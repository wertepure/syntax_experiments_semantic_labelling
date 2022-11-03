
import networkx as nx
from collections import defaultdict


from networkx.drawing.nx_agraph import graphviz_layout
import matplotlib.pyplot as plt
from textwrap import wrap

from estnltk import Text

def get_shortest_paths(G):
    """lyhim tee graafi tippude vahel ning nn reversed kaartega graafist sama"""
    # lyhim tee tippude vahel
    path = nx.all_pairs_shortest_path_length(G)
    path_reversed = nx.all_pairs_shortest_path_length(G.reverse())
    # kauguste maatriksid
    dpath = {x[0]:x[1] for x in path}
    dpath_reversed = {x[0]:x[1] for x in path}
    return {'dict': path,  'dict_reversed': path_reversed, 'matrix': dpath, 'matrix_reversed': dpath_reversed}


def get_prop(graph, property_name):
    """Tagastab array-na syntaksipuu graafi propreteid, tippu 0 ignoreerib"""
    return [graph.nodes[node][property_name] for node in sorted([node for node in graph.nodes]) if node]


def get_nodes_diff(graph1, graph2):
    """leiab, millised tipud suuremast graafist1 on puudu graafis2"""
    return [ node for node in graph1 if not node in graph2 ]


# TODO: clear this function up
def get_nodes_by_attributes(self,  attrname, attrvalue ):
    """Tipu leidmine atribuudi väärtuse järgi"""
    nodes = defaultdict(list)
    {nodes[v].append(k) for k, v in nx.get_node_attributes(self,attrname).items()}
    if attrvalue in nodes:
        return dict(nodes)[attrvalue]
    return []




### eemaldamise funktsioonid

def remove_deprel_ennekui(inputG, rem_deprel):
    """
    Süntaksipuust "enne_kui" eemaldamine
    Eemaldatakse ainult siis, kui advmod lemma on [rohkem, vähem, samapalju, enam]
    ja kui sellele s]nale vahetult järgnes lemma "kui"
    """
    G = inputG.copy()
    #originaallause graaf
    G_original = inputG.copy()

    #tipud eemaldatava depreliga
    rem_deprel_nodes = get_nodes_by_attributes(G, 'deprel', rem_deprel)

    # lemmade nimekiri praegu ei kasuta, vb tuleb t2psustada, mis lemmat eemaldame
    # näiteks, antud juhul võibolla tahame eemaldada ainult seda advmodi, kus on kui-le järgnev sõna või kui
    #lemmas = nx.get_node_attributes(G, "lemma")

    #eemaldame tipud, mis on otsitava deprel'iga
    for n in rem_deprel_nodes:

        #lisatingumus enne_kui jaoks
        if G.nodes[n]['lemma'] in ['rohkem', 'vähem', 'samapalju', 'enam']:
            if n+1 in G.nodes and G.nodes[n+1]['lemma'] == 'kui':
                G.remove_node(n)

    # lyhim tee tippude vahel ja kauguste maatriksid
    paths = graphFunctions.get_shortest_paths(G)
    #paths['matrix'] on dictionary lyhima kaugusega seotud tippudega
    #print ('dpath', dpath)

    #eemaldame kõik tipud, mis pole enam sidusad
    #eeldame siin praegu, et verbi ei eemaldata
    nodes = [node for node in G.nodes]
    for node in nodes:
        if node>0 and not node in paths['matrix'][0]:
            G.remove_node(node)

    deprels = [G.nodes[node]['deprel'] if node in G.nodes else '_' for node in sorted([node for node in G_original.nodes]) if node ]
    return G


#tekst on tokeniseeritud, võib tühikuga otsida küll
def is_enne_kui_examples(G):
    """Kontroll, kas on enne_kui lause"""
    sent = " ".join(this.get_prop(G, 'form').lower())
    kui = [' rohkem kui ', ' vähem kui ', ' samapalju kui ', ' enam kui ']
    for k in kui:
        if k in sent:
            return True
    return False


def add_blanks(a, indexes, blank='_'):
    """Lisab lausesse erisümbolid positsioonidele, kus asusid eemaldatud sõnad"""
    array=a.copy()
    for ind in sorted(indexes):
        array.insert(ind-1, blank)

    return array

def remove_removed(a, indexes):
    """Eemaldab massiivist etteantud positsioonidel asuvad liikmed"""
    #print (array, indexes)
    array=a.copy()
    for ind in reversed(sorted(indexes)):
        array.pop(ind-1)
    return array


def is_equal(arr1, arr2):
    """Tagastab True kui massiivid on võrdsed"""
    if not len(arr1) == len(arr2):
        return False
    for i in range(len(arr1)):
        if not arr1[i] == arr2[i]:
            return False
    return True

def remove_brackets(inputG):
    """Eemaldab sulud, sulgude eemaldamisel ei arvesta süntaksiga"""
    G = inputG.copy()
    # eeldame, et sulud ( ) on peale tokeniseerimist eraldi lemmaks märgendatud
    # läbime Graafi tipud sõnade järjekorras, korjame kokku sellised nodeId
    # mis algavad ( ja lõpevad )
    # eemaldame, ei arvesta süntaksipuu struktuuriga, korjame kokku ainult nodeid-d


    leftNodes1 = []
    leftNodes2 = sorted([n for n in G.nodes])
    nodes_to_remove = []
    while not len(leftNodes1) == len(leftNodes2):

        in_b = False
        leftNodes1 = leftNodes2.copy()
        remove = []
        for n in leftNodes2:
            #ignoreerime null tippu
            if not n: continue
            token = G.nodes[n]['form']
            if not in_b and token == '(':
                remove.append(n)
                in_b = True
                continue
            elif in_b  and  token == '(':
                remove=[]
                remove.append(n)
                in_b = True
                continue
            elif in_b and token == ')':
                #print ('siin break', n, G.nodes[n]['lemma'])
                remove.append(n)
                in_b = False
                break
            elif in_b:
                #print ('siin', n, G.nodes[n]['lemma'])
                remove.append(n)
        #kui lõpeatavad sulgu ei tulnud
        if in_b:
            remove = []
        for n in remove:
            leftNodes2.remove(n)
            nodes_to_remove.append(n)

    for n in nodes_to_remove:
        G.remove_node(n)

    return G

def remove_deprel(G, rem_deprels):

    """Eemaldab süntaksippust etteantud deprel'idega tipud ja nende järglased"""
    if isinstance(rem_deprels, str):
        rem_deprels = [rem_deprels]

    #list unikaalseks
    rem_deprels = list(set(rem_deprels))
    G = G.copy()
    #originaallause graaf
    G_original = G.copy()

    #tipud eemaldatava depreliga

    rem_deprel_nodes = []
    for d in rem_deprels:
        rem_deprel_nodes = rem_deprel_nodes + get_nodes_by_attributes(G, 'deprel', d)

    # lemmade nimekiri praegu ei kasuta, vb tuleb t2psustada, mis lemmat eemaldame
    # näiteks, antud juhul võibolla tahame eemaldada ainult seda advmodi, kus on kui-le järgnev sõna või kui
    #lemmas = nx.get_node_attributes(G, "lemma")

    #eemaldame tipud, mis on otsitava deprel'iga
    for n in rem_deprel_nodes:
        G.remove_node(n)

    # lyhim tee tippude vahel ja kauguste maatriksid
    paths = get_shortest_paths(G)
    #paths['matrix'] on dictionary lyhima kaugusega seotud tippudega
    #print ('dpath', dpath)

    #eemaldame kõik tipud, mis pole enam sidusad
    #eeldame siin praegu, et verbi ei eemaldata
    nodes = [node for node in G.nodes]
    for node in nodes:
        if node>0 and not node in paths['matrix'][0]:
            G.remove_node(node)

    deprels = [G.nodes[node]['deprel'] if node in G.nodes else '_' for node in sorted([node for node in G_original.nodes]) if node ]

    return G

