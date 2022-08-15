# -----------------------------------------------------------
# klass määramiseks, kas lause süntaksipuust tippude eemaldamise järel
# süntaks konnserveerub
# -----------------------------------------------------------
from .. sentence import sentence

import csv
from pathlib import Path
from estnltk.converters.conll_exporter import  sentence_to_conll

import time
import logging
import unicodedata
import re

class Cutter():

    __logger = None
    __stanza_tagger = None
    __Reader = None
    __result_folder = None

    def logInfo(self, messages):
        self.__logger.info(messages)

    # rakenda filter juba olemasolevale süntaktilisele märgendusele
    __use_prefilter = True
    # rakenda filter uuele süntaktilisele märgendusele
    __use_filter = True
    # kasuta ainult originaalset süntaktilist märgendust, ei tee enne lühendamist
    # analüüsi stanza'ga üle
    # nt tuleb kasutada käsitsi märgendatud korpuste korral
    __use_original_syntax = False

    def __init__(self,  **kwargs):

        # create logging, formatter and add it to the handlers
        self.__logger = logging.getLogger('Cutter')
        self.__logger.propagate = False

        set = True
        for handler in self.__logger.handlers:
            set = False
            break
        if set:
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            ch.setFormatter(formatter)
            self.__logger.addHandler(ch)
        # stop propagting to root logger


        if not 'Reader' in kwargs:
            raise Exception("Please specify Reader")
        else:
            self.__Reader  = kwargs['Reader']

        if not 'stanza_tagger' in kwargs:
            raise Exception("Please specify stanza_tagger")
        else:
            self.__stanza_tagger  = kwargs['stanza_tagger']

        if 'result_folder' in kwargs:
            self.__result_folder = kwargs['result_folder']
        if 'use_prefilter' in kwargs and not kwargs['use_prefilter']:
            self.__use_prefilter  = False
        if 'use_filter' in kwargs and not kwargs['use_filter']:
            self.__use_filter  = False
        if 'use_original_syntax' in kwargs and kwargs['use_filter']:
            self.__use_original_syntax  = True


    def pre_filter(self, G, deprel):
        """
            Returns True if sentence has to be filtered out
        """
        deprel_pre =  " ".join(sentence.Sentence.get_prop(G, 'deprel'))
        if not deprel in deprel_pre:
            return True
        else:
            return False

    def filter(self, G, deprel):
        """
            Returns True if sentence has to be filtered out
        """
        deprel_pre =  " ".join(sentence.Sentence.get_prop(G, 'deprel'))
        if not deprel in deprel_pre:
            return True
        else:
            return False

    def cutSentence(self, G, deprel):
        """
            Removes defined deprel out of sentence
            Saves sentences in tsv files
        """
        return sentence.Sentence.remove_deprel(G, deprel)


    def cut(self, deprel):
        """
            Removes nodes with defined deprel from sentences
        """
        self.logInfo(f'Start cutting deprel: {deprel}')


        emptyrow = ('', '', '',  )
        #loome kataloogid
        if self.__result_folder:
            Path(self.__result_folder).mkdir(parents=True, exist_ok=True)
            folder = self.__result_folder
        else:
            #TODO safe folder name
            timestr = time.strftime("%Y%m%d-%H%M%S")
            folderpath = Cutter.slugify(f'{deprel}_{timestr}')
            folder = f'./result/{folderpath}'
            Path("./result").mkdir(parents=True, exist_ok=True)
            Path(folder).mkdir(parents=True, exist_ok=True)

        outuputfile_Stats = f'{folder}/stats.tsv'

        filenameChanged = f'{folder}/changed.tsv'
        filenameConserved = f'{folder}/conserved.tsv'
        filenameConstant = f'{folder}/constant.tsv'
        filenameStats = f'{folder}/stats.tsv'

        f_Changed = open(filenameChanged, 'w')
        f_Conserved = open(filenameConserved, 'w')
        f_Constant = open(filenameConstant, 'w')
        f_Stats = open(filenameStats, 'w')

        # create the csv writer
        wChanged = csv.writer(f_Changed, delimiter='\t')
        wConserved = csv.writer(f_Conserved, delimiter='\t')
        wConstant = csv.writer(f_Constant, delimiter='\t')
        wStats = csv.writer(f_Stats, delimiter='\t')

        cols = ('UID', 'TYPE', 'TEXT', )
        for f in (wChanged, wConserved, wConstant):
            f.writerow(cols,)

        #statistika
        stats = {}
        stats['proc_txt_no'] = 0 # counter for texts
        stats['no_rem_dprels'] = 0   # count number of removed deprels
        stats['no_changed_syntax'] = 0   # count sentences where syntax changed

        stats['sentences_checked'] = 0
        stats['sentences_total'] = 0
        stats['sentences_ignored'] = 0
        stats['sentences_constant'] = 0
        stats['syntax_conserved'] = 0
        stats['syntax_changed'] = 0

        for uid, G in self.__Reader.get_sentences_generator(mode='graph'):
            stats['sentences_total'] += 1
            sentence_text = " ".join(sentence.Sentence.get_prop(G, 'form'))
            deprel_pre =  " ".join(sentence.Sentence.get_prop(G, 'deprel'))

            if self.__use_prefilter and self.pre_filter(G, deprel):
                stats['sentences_ignored'] += 1
                continue
            if self.__use_original_syntax:
                g_origin = G.copy()
            else:
                g_origin = sentence.Sentence.analyze_as_graph(sentence_text, self.__stanza_tagger )

            deprel_origin = sentence.Sentence.get_prop(g_origin, 'deprel')

            #kui deprel pole sees, siis ei kontrolli seda lauset
            #TODO kirjutada üldisem pre_filter funktsioon, mida saab alamklassis üle kirjutada
            if self.__use_filter and self.filter(G, deprel):
                stats['sentences_ignored'] += 1
                continue
            #
            stats['sentences_checked'] += 1

            #teeme uue analüüsi

            #muudame  eemaldame puust vajalikud tipud
            #print ('----')
            #print(G.nodes)
            g_short = self.cutSentence(g_origin, deprel)
            #print(g_short.nodes)



            text_origin = sentence_text
            text_short = " ".join(sentence.Sentence.get_prop(g_short, 'form'))

            #print (text_origin)
            #print (text_short)

            row1 = [str(uid) \
                , 'O'\
                , text_origin ]
            row3 = [str(uid) \
                        , 'DepO'
                        , " ".join(deprel_origin)]

            #kui tekst ei muutunud, siis ei eemaldatud ühtegi tippu
            #selline olukord on võimalik, kui peale uue Stanza analüüsi tegemist
            #tekkinud lausepuus ei leidunud ühtegi otsitud depreliga tippu
            if text_origin == text_short:
                stats['sentences_constant'] += 1
                wConstant.writerow(row1)
                wConstant.writerow(row3)
                wConstant.writerow(emptyrow)
                continue

            #eemaldatud tippude id-d
            nodes_diff = sentence.Sentence.get_nodes_diff(g_origin, g_short)

            #kui originaallausest kadus esimene sõna,
            #keerame lühendatud lause esimese sõna uppercase-ks
            if 1 in nodes_diff:
                text_short = text_short[0].upper() + text_short[1:]

            #teeme lühendatud lausele analüüsi Stanzaga
            #võrdleme originaalpuu ja lühendatud lause süntaksipuu deprel'e

            #uus analüüs lühendatud lausele
            new_graph = sentence.Sentence.analyze_as_graph(text_short, self.__stanza_tagger)

            #lühendatud lause deprel
            deprel_short = sentence.Sentence.get_prop(new_graph, 'deprel')
            #lühendatud lause deprel, kuhu on lisatud _ originaallausest eemaldatud sõnade kohale
            deprel_with_blanks = sentence.Sentence.add_blanks(deprel_short,nodes_diff)

            #originaallause deprel, kuhu on lisatud _ originaallausest eemaldatud sõnade kohale
            original_removed = sentence.Sentence.remove_removed(deprel_origin, nodes_diff)

            conserved = sentence.Sentence.is_equal(deprel_short, original_removed)

            row2 = [str(uid) \
                        , 'S'\
                        , text_short ]


            row4 = [str(uid) \
                        , 'DepS'
                        , " ".join(deprel_with_blanks)]


            if conserved:
                stats['syntax_conserved'] += 1
                wConserved.writerow(row1)
                wConserved.writerow(row2)
                wConserved.writerow(row3)
                wConserved.writerow(row4)
                wConserved.writerow(emptyrow)
            else:
                stats['syntax_changed'] += 1
                wChanged.writerow(row1)
                wChanged.writerow(row2)
                wChanged.writerow(row3)
                wChanged.writerow(row4)
                wChanged.writerow(emptyrow)

            original_removed =  sentence.Sentence.remove_removed(deprel_origin, nodes_diff)

        f_Changed.close()
        f_Conserved.close()
        f_Constant.close()


        for key in stats:
            row = [key, str(stats[key])]
            wStats.writerow(row)


        f_Stats.close()

        self.logInfo(f'Done cutting deprel  {deprel} .')
        self.logInfo(f'Stats stored in {filenameStats} .')


    def slugify(value, allow_unicode=False):
        """
        Taken from https://github.com/django/django/blob/master/django/utils/text.py
        Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
        dashes to single dashes. Remove characters that aren't alphanumerics,
        underscores, or hyphens. Convert to lowercase. Also strip leading and
        trailing whitespace, dashes, and underscores.
        """
        value = str(value)
        if allow_unicode:
            value = unicodedata.normalize('NFKC', value)
        else:
            value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
        value = re.sub(r'[^\w\s-]', '', value.lower())
        return re.sub(r'[-\s]+', '-', value).strip('-_')
