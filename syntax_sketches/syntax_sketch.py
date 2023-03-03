import os, os.path
from random import Random

from estnltk import Layer
from estnltk.converters.conll.conll_importer import conll_to_text

from typing import List, Dict, Union, Any, Tuple, Optional

# =====================================================
#   Creating syntax sketches
# =====================================================

def subtree_size(heads: List[int], tails: List[int], root: int) -> int:
    """
    Computes the size of the subtree specified by the root node, i.e., the root is included into the subtree.
    Arcs of a tree are specified as head, tail pairs, i.e., tails[i] -> heads[i] is an arc.
    """

    result = 0
    for i, dep_head in enumerate(heads):
        if dep_head == root:
            result += subtree_size(heads, tails, tails[i])
    return result + 1


def clean_clause(clause: Layer) -> Dict[str, list]:
    """
    Removes spurious words from clause and extracts relevant information from other layers.
    Spurious words can occur at the beginning or at the end of the clause:
    * conjunctions
    * punctuation marks

    Returns a dictionary of aligned vectors for clause members:
    * ids       -- token numbers
    * postags   -- part-of-speech tags
    * deprels   -- dependency relations
    * heads     -- head of the node
    * root_loc  -- indices of root nodes
    * wordforms -- complete text
    * lemmas    -- lemma
    * features  -- other syntactic features

    Syntax information is specified as in the syntax tree corresponding to the entire sentence.
    As clause finding algorithm is not perfect there can be several roots in the clause.
    The information about root can be found by fetching the corresponding field, e.g. ids[root_loc[0]].
    These fields contain enough information to store the cleaned clause in the conll-format
    """

    # Extract relevant fields
    ids = list(clause.ud_syntax.id)
    postags = list(clause.ud_syntax.xpostag)
    deprels = list(clause.ud_syntax.deprel)
    heads = list(clause.ud_syntax.head)

    wordforms = list(clause.ud_syntax.text)
    lemmas = list(clause.ud_syntax.lemma)
    features = list(clause.ud_syntax.feats)

    # Remove leading punctuation marks and conjunction
    while postags and ('J' in postags[0] or 'Z' in postags[0]):
        heads.pop(0)
        ids.pop(0)
        deprels.pop(0)
        postags.pop(0)
        wordforms.pop(0)
        lemmas.pop(0)
        features.pop(0)

    if not postags:
        return dict(ids=[], postags=[], deprels=[], heads=[], root_loc=[], wordforms=[], lemmas=[], features=[])

    # Remove trailing punctuation marks and conjunction
    while 'J' in postags[-1] or 'Z' in postags[-1]:
        heads.pop()
        ids.pop()
        deprels.pop()
        postags.pop()
        wordforms.pop()
        lemmas.pop()
        features.pop()

    # Find indices of root nodes
    root_locations = [i for i, head in enumerate(heads) if head not in ids]

    return dict(
        ids=ids, postags=postags, deprels=deprels, heads=heads,
        root_loc=root_locations,
        wordforms=wordforms, lemmas=lemmas, features=features)


def syntax_sketch(clause: Dict[str, list], ordered=True) -> str:
    """
    Computes syntax sketch for a clause that encodes information about the root node and the first level child nodes.
    By default the first level child nodes are lexicographically ordered in the sketch.
    
    Examples:
    
    wordforms: ['Ma', 'kaldun', 'arvama']
    ids:       [1, 2, 3]
    heads:     [2, 0, 2]
    postags:   ['P', 'V', 'V']
    deprels:   ['nsubj', 'root', 'xcomp']
    root_loc:  [1]
    output:    '[V]nsubj(L)xcomp(L)'

    wordforms: ['Vermeeri', 'saatus', 'oli', 'teistsugune']
    ids:       [6, 7, 8, 9]
    heads:     [7, 9, 9, 3]
    postags:   ['S', 'S', 'V', 'P']
    deprels:   ['nmod', 'nsubj:cop', 'cop', 'ccomp']
    root_loc:  [3]
    output:    '[S]cop(L)nsubj:cop(L)'
    
    wordforms: ['uus', 'ooper', 'tuleb', 'habras', 'ja', 'ilus']
    ids:       [8, 9, 10, 11, 12, 13]
    heads:     [9, 10, 2, 10, 13, 11]
    postags:   ['A', 'S', 'V', 'A', 'J', 'A']
    deprels:   ['amod', 'nsubj', 'ccomp', 'xcomp', 'cc', 'conj']
    root_loc:  [2]
    output:    '[V]nsubj(L)xcomp(P)'
    """

    assert len(clause['root_loc']) == 1, "The clause must have a single root"

    # Compute root tag for the sketch
    root_tag = clause['postags'][clause['root_loc'][0]]
    if root_tag == 'V':
        # group of verbs
        sketch_root = 'V'
    elif root_tag in ['S', 'P', 'A', 'Y', 'N']:
        # non-verbs: substantives, pronouns, adjectives,
        # acronyms/abbreviations, numerals
        sketch_root = 'S'
    else:
        # remaining postags
        sketch_root = 'X'

    # Compute sketches for child nodes
    first_level = list()
    root = clause['ids'][clause['root_loc'][0]]
    for i, head in enumerate(clause['heads']):
        if head != root:
            continue

        length = subtree_size(clause['heads'], clause['ids'], clause['ids'][i])
        if length < 3:
            subtree_cat = 'L'
        elif length < 10:
            subtree_cat = 'P'
        else:
            subtree_cat = 'ÜP'

        subtree = clause['deprels'][i] + '({})'.format(subtree_cat)
        first_level.append(subtree)

    if ordered:
        return '[{root}]{children}'.format(root=sketch_root, children=''.join(sorted(first_level)))
    else:
        return '[{root}]{children}'.format(root=sketch_root, children=''.join(first_level))


def safe_sketch_name(sketch_name: str) -> str:
    '''
    Makes sketch name safe so that it can be used as (a part of) file name.
    Returns safe name.
    '''
    safe_name = sketch_name.replace(':', 'COLON').replace(')', '').replace('(', '').replace('[', '').replace(']', '')
    assert safe_name.isidentifier()
    return safe_name


# =====================================================
#   Compute sketches for the whole corpus
# =====================================================

def compute_sketches(input_dir:str, skip_files:List[str]=[], verbose:bool=True) -> Tuple[List[str], int]:
    '''
    Loads clauses from conllu files in the input_dir and computes syntax sketches
    for all clauses that have a single root.
    Assumes that all conllu files in the input_dir have been created via script 
    "01b_extract_clauses.py", that is, they contain clauses instead of sentences. 
    Optionally, you can skip some of the input files via parameter skip_files.
    Returns tuple: (list_of_sketches, clauses_count_total) 
    '''
    # 1) Import data from conllu files, rename sentences -> clauses and validate
    expected_layers = {'clauses', 'ud_syntax', 'words'}
    whole_data = []
    for fname in os.listdir(input_dir):
        if fname in skip_files:
            continue
        if fname.endswith('.conllu'):
            text_obj = conll_to_text( os.path.join(input_dir, fname), 
                                      'ud_syntax', 
                                      remove_empty_nodes=True)
            text_obj.meta['file'] = fname
            # Rename sentences layer 
            # (because it actually contains clauses, not sentences)
            clauses_layer = text_obj.pop_layer('sentences')
            clauses_layer.name = 'clauses'
            text_obj.add_layer(clauses_layer)
            # Validate text layers
            assert text_obj.layers == expected_layers, \
                f'Unexpected layers {text_obj.layers!r}'
            whole_data.append(text_obj)
    # 2) Create sketches from the data
    clauses_count_total = 0
    invalid_clauses_total = 0
    sketches = []
    for text_obj in whole_data:
        clauses_count = 0
        for clause in text_obj.clauses:
            cleaned_clause = clean_clause(clause)
            if len(cleaned_clause['root_loc']) != 1:
                # At this point, assuming input processed with 
                # "01b_extract_clauses.py", we actually should 
                # not encounter any invalid clauses ...
                invalid_clauses_total += 1
                continue
            sketches.append(syntax_sketch(cleaned_clause))
            clauses_count += 1
        if verbose:
            print(text_obj.meta['file'], '|', f'#clauses:   {clauses_count}')
        clauses_count_total += clauses_count
    if verbose:
        print()
        print(f'#clauses total:   {clauses_count_total}')
        if invalid_clauses_total > 0:
            print(f'#invalid clauses total:   {invalid_clauses_total}')
    return sketches, clauses_count_total


# =====================================================
#   Distribute syntax sketches randomly into bins
# =====================================================

def rand_group_sketches(sketches: List[Union[str, List[Any]]], n:int, seed:int=5) \
                                             -> List[List[Union[str, List[Any]]]]:
    '''
    Distributes given sketches randomly into n same size groups. 
    Returns list of lists of sketches, one sub list for each group. 
    '''
    result = []
    if not n <= len(sketches):
        raise ValueError(f'(!) Number of sketches ({len(sketches)}) '+\
                         f'is smaller than number of groups ({n}).')
    rnd = Random(seed)
    rnd.shuffle(sketches)
    for i in range(n):
        result.append([])
    for sid, sketch in enumerate(sketches):
        result[sid % n].append(sketch)
    assert len(sketches) == sum([len(g) for g in result])
    return result


# =====================================================
#   Filtering lists of clauses by sketches
# =====================================================

def extract_sketches(clause_conllus: List[str], clause_dicts: List[Dict[str, list]], 
                     target_sketch:str, amount:Optional[int]=None, verbose:bool=False):
    '''
    Extracts given amount of target_sketch from clause_conllus and clause_dicts. 
    Note that the extraction operation is virtual: the input lists clause_conllus 
    and clause_dicts are not affected.
    Returns extracted items. 
    If amount is None (default), then extracts all clauses corresponding to the sketch.
    Returns triple: (extracted_conllus, extracted_dicts, number_of_extracted_items)
    '''
    assert len(clause_conllus) == len(clause_dicts), \
        'Unexpectedly, numers of conllu clauses and corresponding clause dicts differ: '+\
        f' {len(clause_conllus)} vs {len(clause_dicts)}'
    extracted = []
    extracted_dicts = []
    for clause_id, clause_conllu in enumerate(clause_conllus):
        clause_dict = clause_dicts[clause_id]
        sketch = syntax_sketch(clause_dict)
        if sketch == target_sketch:
            if amount is None or len(extracted) < amount:
                extracted.append( clause_conllu )
                extracted_dicts.append( clause_dict )
    if verbose:
        print('Extracted {} instances of sketch {}'. format(len(extracted), target_sketch))
    return extracted, extracted_dicts, len(extracted)


def remove_sketches(clause_conllus: List[str], clause_dicts: List[Dict[str, list]], 
                    target_sketch:str, amount:Optional[int]=None, verbose:bool=False):
    '''
    Removes given amount of target_sketch from clause_conllus and clause_dicts. 
    Note that the removal operation is virtual: the input lists clause_conllus and 
    clause_dicts are not affected.
    Returns preserved items after removal (and count of removed items). 
    If amount is None (default), then removes all clauses corresponding to the sketch.
    Returns triple: (preserved_conllus, preserved_dicts, number_of_removed_items)
    '''
    assert len(clause_conllus) == len(clause_dicts), \
        'Unexpectedly, numers of conllu clauses and corresponding clause dicts differ: '+\
        f' {len(clause_conllus)} vs {len(clause_dicts)}'
    preserved = []
    preserved_dicts = []
    removed = 0
    for clause_id, clause_conllu in enumerate(clause_conllus):
        clause_dict = clause_dicts[clause_id]
        sketch = syntax_sketch(clause_dict)
        if sketch == target_sketch:
            if amount is None or removed < amount:
                removed += 1
                continue
        preserved.append( clause_conllu )
        preserved_dicts.append( clause_dict )
    if verbose:
        print('Removed {} instances of sketch {}'. format(removed, target_sketch))
    return preserved, preserved_dicts, removed


def remove_sketches_group(clause_conllus: List[str], clause_dicts: List[Dict[str, list]], 
                          target_sketches:List[str], verbose:bool=False):
    '''
    Removes all target_sketches from clause_conllus and clause_dicts. 
    Note that the removal operation is virtual: the input lists clause_conllus and 
    clause_dicts are not affected.
    Returns preserved items after the removal (and total count of removed items). 
    Returns triple: (preserved_conllus, preserved_dicts, number_of_removed_items)
    '''
    assert len(clause_conllus) == len(clause_dicts), \
        'Unexpectedly, numers of conllu clauses and corresponding clause dicts differ: '+\
        f' {len(clause_conllus)} vs {len(clause_dicts)}'
    assert len(target_sketches) > 0, 'Unexpectedly, got an empty target_sketches list'
    preserved = []
    preserved_dicts = []
    removed = 0
    target_sketches_set = set(target_sketches)
    for clause_id, clause_conllu in enumerate(clause_conllus):
        clause_dict = clause_dicts[clause_id]
        sketch = syntax_sketch(clause_dict)
        if sketch in target_sketches_set:
            removed += 1
            continue
        preserved.append( clause_conllu )
        preserved_dicts.append( clause_dict )
    if verbose:
        print('Removed {} instances of sketches {}'. format(removed, target_sketches))
    return preserved, preserved_dicts, removed