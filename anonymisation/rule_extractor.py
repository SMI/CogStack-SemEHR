import logging
import utils
import re2 as re


class ExtractRule(object):
    """
    A class of Rule for extraction data from free text
    """
    def __init__(self, rule_files):
        self._rules = {}
        self.load_rule_files(rule_files)

    def load_rule_files(self, rule_files):
        for f in rule_files:
            rules = utils.load_json_data(f)
            for k in rules:
                if k not in self._rules:
                    self._rules[k] = rules[k]
                else:
                    temp_d = self._rules[k].copy()
                    temp_d.update(rules[k])
                    self._rules[k] = temp_d

    @staticmethod
    def rul_extraction(full_text, re_objs):
        results = []
        for ro in re_objs:
            if 'disabled' in ro and ro['disabled']:
                continue
            flag = 0
            if 'multiline' in ro['flags']:
                flag |= re.MULTILINE
            if 'ignorecase' in ro['flags']:
                flag |= re.IGNORECASE
            try:
                matches = re.finditer(ro['pattern'], full_text, flag)
                for m in matches:
                    ret = {'type': ro['data_type'], 'rule': ro['pattern'], 'attrs': {}}
                    results.append(ret)
                    ret['attrs']['full_match'] = m.group(0)
                    ret['pos'] = m.span()
                    i = 1
                    if 'data_labels' in ro:
                        for attr in ro['data_labels']:
                            ret['attrs'][attr] = m.group(i)
                            i += 1
            except Exception as ex:
                import traceback
                logging.error(traceback.format_exc())
                print(ex, ro['pattern'])
        return results

    def do_letter_parsing(self, full_text):
        re_exps = self._rules
        results = []
        header_pos = -1
        tail_pos = -1
        header_result = self.rul_extraction(full_text, [re_exps['letter_header_splitter']])
        tail_result = self.rul_extraction(full_text, [re_exps['letter_end_splitter']])
        results += header_result
        if len(header_result) > 0:
            header_pos = header_result[0]['pos'][0]
            header_text = full_text[:header_pos]
            phone_results = self.rul_extraction(header_text, re_exps['phone'])
            dr_results = self.rul_extraction(header_text, [re_exps['doctor']])
            results += phone_results
            results += dr_results
        if len(tail_result) > 0:
            tail_pos = tail_result[0]['pos'][1]
            tail_text = full_text[tail_pos:]
            for sent_type in re_exps['sent_rules']:
                results += self.rul_extraction(tail_text, re_exps[sent_type])
        return results, header_pos, tail_pos

    def do_full_text_parsing(self, full_text, rule_group='sent_rules'):
        re_exps = self._rules
        matched_rets = []
        for st in re_exps[rule_group]:
            rules = re_exps[rule_group][st]
            matched_rets += self.rul_extraction(full_text, rules if type(rules) is list else [rules])
        return matched_rets, 0, 0

    @staticmethod
    def do_replace(text, pos, sent_text, replace_char='x'):
        return text[:pos] + re.sub(r'[^\n\s]', 'x', sent_text) + text[pos+len(sent_text):]


