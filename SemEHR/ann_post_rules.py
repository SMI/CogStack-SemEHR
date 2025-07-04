import logging
from os.path import join
import re
import SemEHR.utils as utils
import functools # for cmp_to_key

logger = logging.getLogger(__name__)

_text_window = 150
_head_text_window_size = 200


class Rule(object):
    def __init__(self, name, compare_type=-1, containing_pattern=False, case_sensitive=False, more_context_sents=[]):
        self._name = name
        self._compare_type = compare_type
        self._is_containing = containing_pattern
        self._is_case_sensitive = case_sensitive
        self._reg_ptns = []
        self._more_context_sents = more_context_sents

    @property
    def name(self):
        return self._name

    @property
    def compare_type(self):
        return self._compare_type

    @property
    def more_context_sents(self):
        return self._more_context_sents

    @property
    def is_case_sensitive(self):
        return self._is_case_sensitive

    @property
    def is_containing_patterns(self):
        return self._is_containing

    @property
    def reg_patterns(self):
        return self._reg_ptns

    def add_pattern(self, ptn):
        if self.compare_type == -100:
            pass
        elif not self.is_containing_patterns and not ptn.startswith('^') and not ptn.endswith('$'):
            ptn = '^' + ptn + '$'
        elif self.is_containing_patterns:
            ptn = '.*' + ptn + '.*'
        try:
            if self.compare_type == -100:
                reg_p = ptn
            elif self.is_case_sensitive:
                reg_p = re.compile(ptn)
            else:
                reg_p = re.compile(ptn, re.IGNORECASE)
            self._reg_ptns.append(reg_p)
        except Exception:
            logger.error('regs error: [%s]' % ptn)
            exit(1)


class AnnRuleExecutor(object):

    def __init__(self):
        self._text_window = _text_window
        self._filter_rules = []
        self._skip_terms = []
        self._osf_rules = []

    @property
    def skip_terms(self):
        return self._skip_terms

    @skip_terms.setter
    def skip_terms(self, value):
        self._skip_terms = value

    def add_filter_rule(self, token_offset, reg_strs, case_sensitive=False, rule_name='unnamed',
                        containing_pattern=False, more_context_sents=[]):
        rule = Rule(rule_name, compare_type=token_offset,
                    containing_pattern=containing_pattern,
                    case_sensitive=case_sensitive, more_context_sents=more_context_sents)
        for p in reg_strs:
            rule.add_pattern(p)
        self._filter_rules.append(rule)

    @staticmethod
    def relocate_annotation_pos(t, s, e, string_orig):
        if t[s:e] == string_orig:
            return [s, e]
        candidates = []
        ito = re.finditer(r'\b(' + re.escape(string_orig) + r')\b',
                    t, re.IGNORECASE)
        for mo in ito:
            # print mo.start(1), mo.end(1), mo.group(1)
            candidates.append({'dis': abs(s - mo.start(1)), 's': mo.start(1), 'e': mo.end(1), 'matched': mo.group(1)})
        if len(candidates) == 0:
            return [s, e]
        candidates.sort(key=functools.cmp_to_key(lambda x1, x2: x1['dis'] - x2['dis']))
        # print candidates[0]
        return [candidates[0]['s'], candidates[0]['e']]

    def execute(self, text, ann_start, ann_end, string_orig=None):
        # it seems necessary to relocate the original string because of encoding issues
        if string_orig is not None:
            [s, e] = AnnRuleExecutor.relocate_annotation_pos(text, ann_start, ann_end, string_orig)
            ann_start = s
            ann_end = e
        else:
            string_orig = text[ann_start:ann_end]
        s_before = text[max(ann_start - self._text_window, 0):ann_start]
        s_end = text[ann_end:min(len(text), ann_end + self._text_window)]
        # tokens_before = nltk.word_tokenize(s_before)
        # tokens_end = nltk.word_tokenize(s_end)
        # print tokens_before
        # print tokens_end
        filtered = False
        matched = []
        rule_name = ''
        for r in self._filter_rules:
            s_compare = s_end if r.compare_type > 0 else s_before
            if r.compare_type == 0:
                s_compare = text[:_head_text_window_size]
            elif r.compare_type == 100:
                s_compare = string_orig
            # s_compare = s_compare.replace('\n', ' ')
            for reg_p in r.reg_patterns:
                m = reg_p.match(s_compare)
                if m is not None:
                    # print m.group(0)
                    matched.append(m.group(0))
                    rule_name = r.name
                    filtered = True
                    break
        return filtered, matched, rule_name

    def execute_context_text(self, text, s_before, s_end, string_orig, start, end, more_context_sents=None):
        filtered = False
        matched = []
        matched_rules = []
        for r in self._filter_rules:
            rule_name = None
            for st in self.skip_terms:
                if st.lower() == string_orig.lower():
                    return True, [st], 'skip terms'
            s_compare = s_end if r.compare_type > 0 else s_before
            if r.compare_type == 0:
                s_compare = text[:_head_text_window_size]
            elif r.compare_type == 100:
                s_compare = string_orig
            elif r.compare_type == -100:
                in_cut_off = AnnRuleExecutor.cut_off_matching(text, r.reg_patterns, start)
                if in_cut_off:
                    filtered = True
                    matched.append('CUTOFF: %s' % r.name)
                    rule_name = r.name
                    return filtered, matched, rule_name
                else:
                    continue

            if more_context_sents is not None:
                if len(r.more_context_sents) > 0:
                    logger.debug('rule %s more context %s, on %s' % (r.name, r.more_context_sents, more_context_sents))
                    if -1 in r.more_context_sents and 'prev' in more_context_sents:
                        s_compare = '%s %s' % (more_context_sents['prev'], s_compare)
                    if 1 in r.more_context_sents and 'next' in more_context_sents:
                        s_compare = '%s %s' % (s_compare, more_context_sents['next'])
                    logger.debug('s_compare [%s]' % s_compare)
            # s_compare = s_compare.replace('\n', ' ')
            for reg_p in r.reg_patterns:
                m = reg_p.match(s_compare)
                if m is not None:
                    # print m.group(0)
                    matched.append(m.group(0))
                    rule_name = r.name
                    filtered = True
                    logger.debug('%s matched %s' % (s_compare, reg_p.pattern))
                    break
            if rule_name is not None:
                matched_rules.append(rule_name)
        return filtered, matched, matched_rules

    def add_original_string_filters(self, regs):
        self._osf_rules += regs

    def execute_original_string_rules(self, string_orig):
        """
        filter the matching substring using patterns
        :param string_orig:
        :return:
        """
        s_compare = string_orig
        filtered = False
        matched = []
        for r in self._osf_rules:
            try:
                reg_p = re.compile(r)
            except Exception:
                logger.error('regs error: [%s]' % r['regs'])
                exit(1)
            # print 'matching %s on %s' % (reg_p, s_compare)
            m = reg_p.match(s_compare)
            if m is not None:
                # print m.group(0)
                matched.append([m.group(0), r])
                filtered = True
                break
        return filtered, matched

    def load_rule_config(self, config_file):
        rule_config = utils.load_json_data(config_file)
        r_path = rule_config['rules_folder']
        logger.debug('loading rules from [%s]' % r_path)
        for rf in rule_config['active_rules']:
            for r in utils.load_json_data(join(r_path, rf)):
                self.add_filter_rule(r['offset'], r['regs'], rule_name=rf,
                                     case_sensitive=r['case_sensitive'] if 'case_sensitive' in r else False,
                                     containing_pattern=r['containing_pattern'] if 'containing_pattern' in r else False,
                                     more_context_sents=r['more_context_sents'] if 'more_context_sents' in r else [])
            logger.debug('%s loaded' % rf)
        if 'osf_rules' in rule_config:
            for osf in rule_config['osf_rules']:
                self.add_original_string_filters(utils.load_json_data(join(r_path, osf)))
                logger.debug('original string filters from [%s] loaded' % osf)
        if 'skip_term_setting' in rule_config:
            self.skip_terms = utils.load_json_data(rule_config['skip_term_setting'])

    @staticmethod
    def cut_off_matching(text, anchor_texts, check_pos):
        for t in anchor_texts:
            pos = text.lower().find(t.lower())
            if check_pos >= pos > 0:
                return True
        return False


def test_filter_rules():
    t = """Sheet1
    Application for Appointeeship/court
    ACaCac clincic for check up
    """
    e = AnnRuleExecutor()
    # e.add_filter_rule(1, [r'.{0,5}\s+yes'], case_sensitive=False)
    e.load_rule_config('./studies/autoimmune.v3/sample_rule_config.json')
    # rules = utils.load_json_data('./studies/rules/negation_filters.json')
    # for r in rules:
    #     print r
    #     e.add_filter_rule(r['offset'], r['regs'], case_sensitive=True if 'case' in r and r['case'] is True else False)
    print('working on [%s]' % t)
    print(e.execute_context_text(t, 'ACaCac', ' clinic', 'clincic'))


def test_osf_rules():
    t = "ADAD-A"
    e = AnnRuleExecutor()
    e.load_rule_config('./studies/autoimmune.v3/sample_rule_config.json')
    # rules = utils.load_json_data('./studies/rules/osf_acroynm_filters.json')
    # e.add_original_string_filters(rules)
    print(e.execute_original_string_rules(t))


if __name__ == "__main__":
    logging.basicConfig(level='DEBUG')
    test_filter_rules()
    # [s, e] = AnnRuleExecutor.relocate_annotation_pos("""
    # i am a very long string
    # with many characters, liver
    #  such as Heptaitis C, LIver and Candy
    # """, 77, 15, 'liver')
    # print s, e
