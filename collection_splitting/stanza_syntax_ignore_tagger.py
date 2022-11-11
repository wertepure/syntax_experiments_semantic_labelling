import os
from collections import OrderedDict
from random import Random

from estnltk import Layer
from estnltk.taggers.standard.syntax.syntax_dependency_retagger import SyntaxDependencyRetagger
from estnltk_neural.taggers.syntax.stanza_tagger.stanza_tagger import StanzaSyntaxTagger
from estnltk.taggers.standard.syntax.ud_validation.deprel_agreement_retagger import DeprelAgreementRetagger
from estnltk.taggers.standard.syntax.ud_validation.ud_validation_retagger import UDValidationRetagger
from estnltk.taggers import Tagger
from estnltk.converters.serialisation_modules import syntax_v0
from estnltk.downloader import get_resource_paths

from estnltk import Text


class StanzaSyntaxIgnoreTagger(Tagger):
    """
    This is an entity ignore tagger that creates a layer with the subtrees from stanza_syntax_ignore_entity layer
    "removed" so that the spans will have None values. The short sentence after subtree removal is tagged with 
    StanzaSyntaxTagger and the nwe spans are added to the output layer of this tagger.
    """
    
    conf_param = ['model_path', 'add_parent_and_children', 'syntax_dependency_retagger',
                  'input_type', 'dir', 'mark_syntax_error', 'mark_agreement_error', 'agreement_error_retagger',
                  'ud_validation_retagger', 'resources_path']

    def __init__(self,
                 output_layer='stanza_syntax_without_entity',
                 sentences_layer='sentences',
                 words_layer='words',
                 input_morph_layer='morph_analysis',
                 stanza_syntax_layer = "stanza_syntax",
                 stanza_deprel_ignore_layer = "stanza_syntax_ignore_entity",
                 input_type='morph_extended',  # or 'morph_extended', 'sentences'
                 add_parent_and_children=False,
                 depparse_path=None,
                 resources_path=None,
                 mark_syntax_error=False,
                 mark_agreement_error=False,
                 ):
        # Make an internal import to avoid explicit stanza dependency
        import stanza

        self.add_parent_and_children = add_parent_and_children
        self.mark_syntax_error = mark_syntax_error
        self.mark_agreement_error = mark_agreement_error
        self.output_layer = output_layer
        self.output_attributes = ('id', 'lemma', 'upostag', 'xpostag', 'feats', 'head', 'deprel', 'deps', 'misc', "status")
        self.input_type = input_type
        self.resources_path = resources_path

        if not resources_path:
            # Try to get the resources path for stanzasyntaxtagger. Attempt to download resources, if missing
            self.dir = get_resource_paths("stanzasyntaxtagger", only_latest=True, download_missing=True)
        else:
            self.dir = resources_path
        # Check that resources path has been set
        if self.dir is None:
            raise Exception('Models of StanzaSyntaxTagger are missing. '+\
                            'Please use estnltk.download("stanzasyntaxtagger") to download the models.')

        self.syntax_dependency_retagger = None
        if add_parent_and_children:
            self.syntax_dependency_retagger = SyntaxDependencyRetagger(conll_syntax_layer=output_layer)
            self.output_attributes += ('parent_span', 'children')

        self.ud_validation_retagger = None
        if mark_syntax_error:
            self.ud_validation_retagger = UDValidationRetagger(output_layer=output_layer)
            self.output_attributes += ('syntax_error', 'error_message')

        self.agreement_error_retagger = None
        if mark_agreement_error:
            if not add_parent_and_children:
                raise ValueError('`add_parent_and_children` must be True for marking agreement errors.')
            else:
                self.agreement_error_retagger = DeprelAgreementRetagger(output_layer=output_layer)
                self.output_attributes += ('agreement_deprel',)

        if self.input_type not in ['sentences', 'morph_analysis', 'morph_extended', "stanza_syntax"]:
            raise ValueError('Invalid input type {}'.format(input_type))

        # Check for illegal parameter combinations (mismatching input type and layer):
        if input_type=='morph_analysis' and input_morph_layer=='morph_extended':
            raise ValueError( ('Invalid parameter combination: input_type={!r} and input_morph_layer={!r}. '+\
                              'Mismatching input type and layer.').format(input_type, input_morph_layer))
        elif input_type=='morph_extended' and input_morph_layer=='morph_analysis':
            raise ValueError( ('Invalid parameter combination: input_type={!r} and input_morph_layer={!r}. '+\
                              'Mismatching input type and layer.').format(input_type, input_morph_layer))

        if depparse_path and not os.path.isfile(depparse_path):
            raise ValueError('Invalid path: {}'.format(depparse_path))
        elif depparse_path and os.path.isfile(depparse_path):
            self.model_path = depparse_path
        else:
            if input_type == 'morph_analysis':
                self.model_path = os.path.join(self.dir, 'et', 'depparse', 'morph_analysis.pt')
            if input_type == 'morph_extended' or input_type == "stanza_syntax":
                self.model_path = os.path.join(self.dir, 'et', 'depparse', 'morph_extended.pt')
            if input_type == 'sentences':
                self.model_path = os.path.join(self.dir, 'et', 'depparse', 'stanza_depparse.pt')

        if not os.path.isfile(self.model_path):
            raise FileNotFoundError('Necessary models missing, download from https://entu.keeleressursid.ee/public-document/entity-9791 '
                             'and extract folders `depparse` and `pretrain` to root directory defining '
                             'StanzaSyntaxTagger under the subdirectory `stanza_resources/et (or set )`')

        if input_type == 'sentences':
            if not os.path.isfile(os.path.join(self.dir, 'et', 'pretrain', 'edt.pt')):
                raise FileNotFoundError(
                    'Necessary pretrain model missing, download from https://entu.keeleressursid.ee/public-document/entity-9791 '
                    'and extract folder `pretrain` to root directory defining '
                    'StanzaSyntaxTagger under the subdirectory `stanza_resources/et`')

        if self.input_type == 'sentences':
            self.input_layers = [sentences_layer, words_layer]

        elif self.input_type in ['morph_analysis', 'morph_extended', "stanza_syntax"]:
            self.input_layers = [sentences_layer, input_morph_layer, words_layer, stanza_syntax_layer, stanza_deprel_ignore_layer]            


    def _make_layer_template(self):
        """Creates and returns a template of the layer."""
        layer = Layer(name=self.output_layer,
                      text_object=None,
                      attributes=self.output_attributes,
                      parent=self.input_layers[3],
                      ambiguous=False )
        if self.add_parent_and_children:
            layer.serialisation_module = syntax_v0.__version__
        return layer


    def _make_layer(self, text, layers, status=None):
        # Make an internal import to avoid explicit stanza dependency
        
        rand = Random()
        rand.seed(4)
        
        stanza_syntax_layer = layers[self.input_layers[3]]
        stanza_deprel_ignore_layer = layers[self.input_layers[4]]

        layer = self._make_layer_template()
        layer.text_object=text

        short_sent = text.text 
        subtree_replaced_sent = text.text 
        # remove subtrees from sentence 
        for span in stanza_deprel_ignore_layer.spans:
            subtree = " ".join([w.text for w in span.words])
            short_sent = short_sent.replace(subtree, "")
            subtree_replaced_sent = subtree_replaced_sent.replace(subtree, "_ "*len(span.words)).replace("  ", " ")
        
        # initiate stanza tagger 
        stanza_tagger = StanzaSyntaxTagger(input_type=self.input_type, input_morph_layer=self.input_type, 
                                            add_parent_and_children=True, resources_path=self.resources_path)
        # tag the "short" sentence
        txt = Text(short_sent)
        txt.tag_layer('morph_extended')
        stanza_tagger.tag( txt )
        
        # iterate over sentence where replaced subtree is replaced with "_"-s
        subtracted_words_counter = 0
        for i, word in enumerate(subtree_replaced_sent.split(" ")):
            if word == "_":
                subtracted_words_counter+= 1
                span = list(stanza_syntax_layer.spans)[i]
                attributes = {'id': None, 'lemma': None, 'upostag': None, 'xpostag': None, 'feats': None,
                      'head': None, 'deprel': None, "status": "removed", 'deps': '_', 'misc': '_'}
            
                layer.add_annotation(span, **attributes)
            else:
                # take old span and add new attributes
                span = list(stanza_syntax_layer.spans)[i]
                new_span = list(txt.stanza_syntax.spans)[i-subtracted_words_counter]
                if 'feats' in txt.stanza_syntax.attributes:
                    feats = new_span['feats']
                
                attributes = {'id': new_span.id, 'lemma': new_span['lemma'], 'upostag': new_span['upostag'], 'xpostag': new_span['xpostag'], 'feats': feats,
                                'head': new_span['head'], 'deprel': new_span['deprel'], "status": "remained", 'deps': '_', 'misc': '_'}
                
                layer.add_annotation(span, **attributes)
        
    
        if self.add_parent_and_children:
            # Add 'parent_span' & 'children' to the syntax layer.
            #print(self.output_layer, layer)
            self.syntax_dependency_retagger.change_layer(text, {self.output_layer: layer})

        if self.mark_syntax_error:
            # Add 'syntax_error' & 'error_message' to the layer.
            self.ud_validation_retagger.change_layer(text, {self.output_layer: layer})

        if self.mark_agreement_error:
            # Add 'agreement_deprel' to the layer.
            self.agreement_error_retagger.change_layer(text, {self.output_layer: layer})

        return layer


def feats_to_ordereddict(feats_str):
    """
    Converts feats string to OrderedDict (as in MaltParserTagger and UDPipeTagger)
    """
    feats = OrderedDict()
    if feats_str == '_':
        return feats
    feature_pairs = feats_str.split('|')
    for feature_pair in feature_pairs:
        key, value = feature_pair.split('=')
        feats[key] = value
    return feats