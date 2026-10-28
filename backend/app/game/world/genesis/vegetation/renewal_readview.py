"""Transaction-local memoization of E1's existing evaluator, without changing E1.

Only fields actually read by the pinned E1 evaluator enter each typed key. The
original evaluate/classify implementations produce every value. Neither facts,
physical fields, thresholds nor taxonomy are modified. The private sampler's
normal deep-copy boundary keeps cached result rows inaccessible to callers.
"""
from collections import OrderedDict
from copy import copy
from . import lifecycle as life
from ..environment.classifier import NaturalClassifier,LAND_ROLES,FEATURE_GUARDS,CONFIRMATION_GUARDS,numeric


def immutable(*args,**kwargs):raise TypeError('Transaction-local E1 evaluation is read-only')


class ResultList(list):
    __setitem__=__delitem__=append=clear=extend=insert=pop=remove=reverse=sort=__iadd__=__imul__=immutable
    def __deepcopy__(self,memo):return self


class Result(dict):
    __setitem__=__delitem__=clear=pop=popitem=setdefault=update=__ior__=immutable
    def __deepcopy__(self,memo):return self


def freeze(result):return Result({k:ResultList(v) if isinstance(v,list) else v for k,v in result.items()})


class ClassifierMemo:
    def __init__(self,original):
        self.original=original;self.compiled=original.compiled;self.config=original.config;self.catalog=original.catalog
        self.cache=OrderedDict();self.hits=0;self.misses=0;self.fields={};self.buckets={};self.normalized=None
        for identifier,compiled in self.compiled.items():
            rule=self.catalog['rules'][identifier];fields={f for f,_ in compiled}
            fields.update(x['campo_canonico_proposto'] for x in rule['evidencias_fisicas_obrigatorias_all'])
            fields.update(x['campo_canonico_proposto'] for x in rule['criterios_sazonais_referencia'])
            fields.update(CONFIRMATION_GUARDS.get(identifier,[]));fields.update(FEATURE_GUARDS.get(identifier,[]))
            if rule['papel_espacial_principal'] in LAND_ROLES:fields.add('terreno.evidencia_superficie_continental')
            if self.catalog['natural'][identifier]['grupo']=='florestas':fields.add('clima.periodo_mais_quente_c')
            self.fields[identifier]=tuple(sorted(fields))
            external={x['campo_canonico_proposto'] for x in rule['evidencias_fisicas_obrigatorias_all']}
            external.update(x['campo_canonico_proposto'] for x in rule['criterios_sazonais_referencia'])
            external.update(FEATURE_GUARDS.get(identifier,[]));external.update(CONFIRMATION_GUARDS.get(identifier,[]))
            if rule['papel_espacial_principal'] in LAND_ROLES:external.add('terreno.evidencia_superficie_continental')
            if self.catalog['natural'][identifier]['grupo']=='florestas':external.add('clima.periodo_mais_quente_c')
            groups={}
            for field,bounds in compiled:groups.setdefault(field,[]).append(bounds)
            # E1 assigns a constant score to topographic ranges. Exact altitude/
            # slope is irrelevant to the result inside each inclusive interval.
            for field,bounds in groups.items():
                if field not in external and (field.startswith('terreno.') or all(lo==hi for lo,hi in bounds)):
                    self.buckets[identifier,field]=bounds

    def evaluate(self,identifier,facts,*,backend_guards=True):
        values=[]
        for field in self.fields[identifier]:
            bounds=self.buckets.get((identifier,field))
            if bounds is not None:
                if self.normalized is not None:
                    if field not in self.normalized:self.normalized[field]=numeric(facts.get(field))
                    value=self.normalized[field]
                else:value=numeric(facts.get(field))
                values.append(('interval_class',None if value is None else tuple(lo<=value<=hi for lo,hi in bounds)))
            else:values.append((type(facts.get(field)),facts.get(field)))
        values=tuple(values)
        key=(identifier,backend_guards,values)
        try:hash(key)
        except TypeError:return self.original.evaluate(identifier,facts,backend_guards=backend_guards)
        found=self.cache.get(key)
        if found is not None:
            self.hits+=1;self.cache.move_to_end(key);return found
        self.misses+=1;found=freeze(self.original.evaluate(identifier,facts,backend_guards=backend_guards))
        self.cache[key]=found
        while len(self.cache)>8192:self.cache.popitem(last=False)
        return found

    def classify(self,facts):
        self.normalized={}
        try:return NaturalClassifier.classify(self,facts)
        finally:self.normalized=None


def read_view(sampler):
    view=copy(sampler);environment=copy(sampler.environment)
    environment.classifier=ClassifierMemo(sampler.environment.classifier);environment.cache=OrderedDict()
    view.environment=environment;return view
