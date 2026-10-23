import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from extraction_checks import check_extraction
from prompt_data import compact_checker_context, model_view


def test_record_checks_fail_bad_id_line_and_unit_but_do_not_certify_meaning():
    source={'id':'s','text':'L01 Mix for 2 minutes.\nL02 Ferment 18 hours at 20 C.'}
    result={'answer':'Mix for 2 minutes.','gaps':[], 'sources':[{'id':'s','locator':'s:L01'}]}
    assert check_extraction(result,[source])['verdict']=='REVIEW'
    result['answer']='Mix for 2 hours.'
    assert check_extraction(result,[source])['verdict']=='FAIL'


def test_attached_source_units_and_expanded_output_units_are_equivalent():
    source={'id':'s','text':'L01 Ferment 24hr; use 30 grams salt and 600ml water.'}
    result={'answer':'Ferment 24 hours; use 30 g salt and 600 ml water.','gaps':[], 'sources':[{'id':'s','locator':'s:L01'}]}
    assert check_extraction(result,[source])['verdict']=='REVIEW'


def test_short_support_quote_does_not_hide_other_supplied_lines():
    source={'id':'s','text':'L01 Use 30 grams salt.\nL02 Rest 24hr at 20 C.'}
    result={'answer':'Use 30 g salt. Rest 24 hours at 20 C.','gaps':[],
            'sources':[{'id':'s','locator':'s:L01-L02','support_excerpt':'L01 Use 30 grams salt.'}]}
    assert check_extraction(result,[source])['verdict']=='REVIEW'
    result['answer']='Mix for 2 minutes (L99).'
    assert check_extraction(result,[source])['verdict']=='FAIL'
    result['sources'][0]['id']='wrong'
    assert check_extraction(result,[source])['verdict']=='FAIL'


def test_prompt_view_removes_paths_and_internal_fields_deduplicates_full_source():
    source={'id':'fixture:s','locator':'C:\\Users\\private\\source.txt','text':'L01 Mix.' ,'sha256':'abc'}
    result={'answer':'Mix.','sources':[{'id':'fixture:s','locator':source['locator'],'support_excerpt':'L01 Mix.'}],
            'gaps':[], 'policy':{'prompt_hash':'secret'}}
    context=compact_checker_context({'candidates':[{'id':str(i),'contract':{'inputs':[source['locator']]},'result':result,'supplied_sources':[source]} for i in (1,2)]})
    assert len(context['source_registry'])==1
    assert context['source_registry'][0]['locator']=='fixture:s'
    assert 'policy' not in context['candidates'][0]['result']
    assert 'support_excerpt' not in context['candidates'][0]['result']['sources'][0]
    assert context['candidates'][0]['contract']['inputs']==['fixture:s']
