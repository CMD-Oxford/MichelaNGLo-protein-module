__description__ = """
The class ProteinAnalyser builds upon the ProteinLite core and expands it with 
"""

from .core import ProteinCore
from .mutation import Mutation
import re
import io, os
from .analyse import StructureAnalyser

class ProteinAnalyser(ProteinCore):
    ptm_definitions = {'p': 'phosphorylated',
                       'ub': 'ubiquitinated',
                       'ga': 'O-galactosylated',
                       'm1': 'methylated',
                       'm2': 'dimethylated',
                       'm3': 'trimethylated'}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        ### other ###
        ### mutation ###
        self._mutation = None
        ## structure
        self.structure = None #StructureAnalyser instance

    ############## elm
    _elmdata = []

    @property
    def elmdata(self):
        ### load only when needed basically...
        if not len(self._elmdata):
            with open(os.path.join(self.settings.reference_folder, 'elm_classes.tsv')) as fh:
                header = ("Accession", "ELMIdentifier", "FunctionalSiteName", "Description", "Regex", "Probability",
                          "#Instances", "#Instances_in_PDB")
                for line in fh:
                    if line[0] == '#':
                        continue
                    if "Accession" in line:
                        continue
                    self._elmdata.append(dict(zip(header, line.replace('"', '').split('\t'))))
            self.__class__._elmdata = self._elmdata  ## change the class attribute too!
        return self._elmdata

    def _set_mutation(self, mutation):
        if isinstance(mutation, str):
            self._mutation = Mutation(mutation)
        else:
            self._mutation = mutation

    mutation = property(lambda self:  self._mutation, _set_mutation)

    # decorator no longer used.
    def _sanitise_position(fun):
        """
        Decorator that makes sure that position is a number. It is a bit unnecassary for a one job task...
        :return: int,
        """
        def sanitiser(self, position):
            if isinstance(position, str):
                position = int(position)
            elif isinstance(position, int):
                pass
            elif not isinstance(position, int):
                position = position.residue_index
            elif position == None:
                position = self.mutation.residue_index
            else:
                position = position
            return fun(self, position)

        return sanitiser


    def _neighbours(self, midresidue, position, marker='*', span=10):
        """
        Gets the 10 AA stretch for mutant or not.

        :param midresidue: what is the letter to put in middle. Used for wt and mutant.
        :param position: number
        :param marker: '*' to surround the midresidue.
        :param span: length of span. default 10.
        :return: 10 aa span.
        """
        halfspan = int(span / 2)
        if position < 5:
            neighbours = '{pre}{m}{i}{m}{post}'.format(pre=self.sequence[:position - 1],
                                                       i=midresidue,
                                                       post=self.sequence[position:position + halfspan],
                                                       m=marker)
        elif position > 5 and len(self.sequence) > position + halfspan:
            neighbours = '{pre}{m}{i}{m}{post}'.format(pre=self.sequence[position - 1 - halfspan:position - 1],
                                                       i=midresidue,
                                                       post=self.sequence[position:position + halfspan],
                                                       m=marker)
        elif len(self.sequence) < position + 5:
            neighbours = '{pre}{m}{i}{m}{post}'.format(pre=self.sequence[position - 1 - halfspan:position - 1],
                                                       i=midresidue,
                                                       post=self.sequence[position:],
                                                       m=marker)
        else:
            neighbours = 'ERROR.'
        return neighbours

    ################### mutant related
    def predict_effect(self):
        """
        main entry point for analyses.
        Do note that there is another class called StructureAnalyser which deals with the model specific details.
        :return:
        """
        assert self.mutation, 'No mutation specified.'
        if self.mutation:
            if not self.check_mutation():
                raise ValueError(self.mutation_discrepancy())
        self.check_elm()
        affected = {}
        affected['features'] = self.get_features_at_position()
        #self.analyse_structure()

    def check_mutation(self):
        if len(self.sequence) > self.mutation.residue_index and \
            self.sequence[self.mutation.residue_index - 1] == self.mutation.from_residue and \
            self.mutation.to_residue in 'ACDEFGHIKLMNPQRSTVWY':
            return True
        else:
            return False  # call mutation_discrepancy to see why.

    def mutation_discrepancy(self):
        # returns a string explaining the `check_mutation` discrepancy error
        neighbours = ''
        #print(self.mutation.residue_index, len(self.sequence), self.sequence[self.mutation.residue_index - 1], self.mutation.from_residue)
        if len(self.sequence) < self.mutation.residue_index:
            return 'Uniprot {g} is only {l} amino acids long, while user claimed a mutation at {i}.'.format(
                g=self.uniprot,
                i=self.mutation.residue_index,
                l=len(self.sequence)
            )
        elif self.sequence[self.mutation.residue_index - 1] != self.mutation.from_residue:
            neighbours = self._neighbours(midresidue=self.sequence[self.mutation.residue_index - 1],
                                          position=self.mutation.residue_index,
                                          marker='*')
            return 'Residue {i} is {n} in Uniprot {g}, while user claimed it was {f}. (neighbouring residues: {s}'.format(
                i=self.mutation.residue_index,
                n=self.sequence[self.mutation.residue_index - 1],
                g=self.uniprot,
                f=self.mutation.from_residue,
                s=neighbours
            )
        elif self.mutation.to_residue not in 'ACDEFGHIKLMNPQRSTVWY':
            return 'Analysis can only deal with missenses right now.'
        else:
            raise ValueError(f'Unable to analyse {self.uniprot} for mysterious reasons (resi:{self.mutation.residue_index}, from:{self.mutation.from_residue}, to:{self.mutation.to_residue})')

    ################################# ELM

    def _rex_elm(self, neighbours:str, regex:str, starter:bool=False, ender:bool=False):
        """
        The padding in neighbours is to stop ^ and $ matching.
        :param neighbours: sequence around the mutation
        :type neighbours: str
        :param regex: ELM regex
        :type regex: str
        :param starter: is it at the start?
        :param ender: is it at the end?
        :return: None or tuple(start:int, stop:int)
        """
        if starter:
            offset = 0
            rex = re.search(regex, neighbours + 'XXX')
        elif ender:
            offset = 3
            rex = re.search(regex, 'X' * offset +neighbours)
        else:
            offset = 3
            rex = re.search(regex, 'X' * offset + neighbours + 'X' * offset)
        if rex:
            return (rex.start() - offset, rex.end() - offset)
        else:
            return False

    def check_elm(self):
        assert self.sequence, 'No sequence defined.'
        position = self.mutation.residue_index
        neighbours = self._neighbours(midresidue=self.sequence[position - 1], position=position, span=10, marker='')
        mut_neighbours = self._neighbours(midresidue=self.mutation.to_residue, position=position, span=10, marker='')
        results = []
        elm = self.elmdata
        for r in elm:
            starter = position < 5
            ender = position + 5 > len(self.sequence)
            w = self._rex_elm(neighbours, r['Regex'], starter, ender)
            m = self._rex_elm(mut_neighbours, r['Regex'], starter, ender)
            if w != False or m != False:
                match = {'name': r['FunctionalSiteName'],
                         'description': r['Description'],
                         'regex': r['Regex'],
                         'probability': float(r['Probability'])}
                if w != False and m != False:
                    match['x'] = w[0] + position - 5
                    match['y'] = w[1] + position - 5
                    match['status'] = 'kept'
                elif w != False and m == False:
                    match['x'] = w[0] + position - 5
                    match['y'] = w[1] + position - 5
                    match['status'] = 'lost'
                else:
                    match['x'] = m[0] + position - 5
                    match['y'] = m[1] + position - 5
                    match['status'] = 'gained'
                results.append(match)
        self.mutation.elm = sorted(results, key=lambda m: m['probability'] + int(m['status'] == 'kept'))
        return self

    ##################### Position queries.

    def get_features_at_position(self, position=None):
        """
        :param position: mutation, str or position
        :return: list of gnomAD mutations, which are dictionary e.g. {'id': 'gnomAD_19_19_rs562294556', 'description': 'R19Q (rs562294556)', 'x': 19, 'y': 19, 'impact': 'MODERATE'}
        """
        position = position if position is not None else self.mutation.residue_index
        return self.get_features_near_position(position, wobble=0)

    def get_features_near_position(self, position=None, wobble=10):
        position = position if position is not None else self.mutation.residue_index
        valid = []
        for g in self.features:
            for f in self.features[g]:
                if 'x' in f:
                    if f['x'] - wobble < position and position < f['y'] + wobble:
                        valid.append({**f, 'type': g})
                elif 'residue_index':
                    if f['residue_index'] - wobble < position and position < f['residue_index'] + wobble:
                        ## PTM from phosphosite plus are formatted differently. the feature viewer and the .structural known this.
                        valid.append({'x': f['residue_index'], 'y': f['residue_index'], 'description': self.ptm_definitions[f['ptm']], 'type': 'Post translational'})
        svalid = sorted(valid, key=lambda v: int(v['y']) - int(v['x']))
        return svalid

    def get_gnomAD_near_position(self, position=None, wobble=5):
        """
        :param position: mutation, str or position
        :param wobble: int, number of residues before and after.
        :return: list of gnomAD mutations, which are named touples e.g. {'id': 'gnomAD_19_19_rs562294556', 'description': 'R19Q (rs562294556)', 'x': 19, 'y': 19, 'impact': 'MODERATE'}
        """
        position = position if position is not None else self.mutation.residue_index
        #valid = [g for g in self.gnomAD if g.x - wobble < position < g.y + wobble]
        #svalid = sorted(valid, key=lambda v: v.y - v.x)
        valid = {g.description: g for g in self.gnomAD if g.x - wobble < position < g.y + wobble}
        svalid = sorted(valid.values(), key=lambda v: v.x)
        return svalid

    # def _get_structures_with_position(self, position):
    #     """
    #     Fetches structures that exists at a given position.
    #     :param position: mutation, str or position
    #     :return: list of self.pdbs+self.swissmodel+self.pdb_matches...
    #     """
    #     print('Use get_best_model')
    #     raise DeprecationWarning
    #     return [pdb for pdb in self.pdbs + self.swissmodel + self.pdb_matches if int(pdb['x']) < position < int(pdb['y'])]

    def get_best_model(self):
        """
        This currently just gets the first PDB based on resolution. It ought to check what is the best properly.
        it checks pdbs first, then swissmodel.
        :return:
        """
        for l in (self.pdbs, self.swissmodel):
            if l:
                good = []
                for model in l: #model is a structure object.
                    if model.includes(self.mutation.residue_index):
                        good.append(model)
                if good:
                    good.sort(key=lambda x: x.resolution)
                    return good[0]
                else: # no models with mutation.
                    pass
            else: #no models in group
                pass
        return None

    @property
    def property_at_mutation(self):
        return {k: self.properties[k][self.mutation.residue_index -1] for k in self.properties}

    def analyse_structure(self):
        structure = self.get_best_model()
        #structure id a michelanglo_protein.core.Structure object
        if not structure:
            self.structural = None
            return self
        self.structural = StructureAnalyser(structure, self.mutation)
        if self.structural and self.structural.neighbours:
            ## see mutation.exposure_effect
            self.mutation.surface_expose = 'buried' if self.structural.buried else 'surface'
            self.annotate_neighbours()
        return self


    def annotate_neighbours(self):
        """
        The structural neighbours does not contain data re features.
        :return:
        """
        for neigh in self.structural.neighbours:
            neigh['resn'] = Mutation.aa3to1(neigh['resn'])
            if neigh['chain'] != 'A':
                neigh['detail'] = 'interface'
            else:
                specials = []
                r = int(neigh['resi'])
                gnomad = ['gnomAD:' + g.description for g in self.gnomAD if r == g.x]
                specials.extend(gnomad)
                for k in ('initiator methionine',
                          'modified residue',
                          'glycosylation site',
                          'non-standard amino acid'):
                    if k in self.features:
                        specials.extend(['PTM:' + m['description'] for m in self.features[k] if r == m['x']])
                if 'PSP_modified_residues' in self.features:
                    specials.extend(
                        ['PTM:' + self.ptm_definitions[m['ptm']] for m in self.features['PSP_modified_residues'] if
                         r == m['residue_index']])
                neigh['detail'] = ' / '.join(specials)

    # conservation score
    # disorder




