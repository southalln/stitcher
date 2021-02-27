import os, sys, json, requests, argparse

LUT = {}
API = {}
TOKEN = ''

def set_id(s, d):
    if 'Id' in d:
        s['Id'] = d['Id']

def set_gene_id(s, d):
    if 'Id' in d:
        s['Id'] = d['Id']
        s['gene_sfdc_id'] = d['Gene_Gene_Symbol__c']

def set_phenotype_id(s, d):
    if 'Id' in d:
        s['Id'] = d['Id']        
        s['phenotype_sfdc_id'] = d['Feature__c']

def set_drug_id(s, d):
    if 'Id' in d:
        s['Id'] = d['Id']
        s['drug_sfdc_id'] = d['Drug__c']
    
def _smash(array, r, type, fn = set_id):
    data = []
    for x in r:
        if x['attributes']['type'] == type:
            data.append(x)
    for (i,s) in enumerate(array):
        fn(s, data[i])

def smash(d, r):
    _smash (d['disease_categories'], r, 'GARD_Disease_Category__c')
    _smash (d['synonyms'], r, 'Disease_Synonym__c')
    _smash (d['external_identifiers'], r, 'External_Identifier_Disease__c')
    _smash (d['inheritance'], r, 'Inheritance__c')
    _smash (d['age_at_onset'], r, 'Age_At_Onset__c')
    _smash (d['age_at_death'], r, 'Age_At_Death__c')
    _smash (d['diagnosis'], r, 'Diagnosis__c')
    _smash (d['epidemiology'], r, 'Epidemiology__c')
    _smash (d['genes'], r, 'GARD_Disease_Gene__c', set_gene_id)
    _smash (d['phenotypes'], r, 'GARD_Disease_Feature__c', set_phenotype_id)
    _smash (d['drugs'], r, 'GARD_Disease_Drug__c', set_drug_id)
    _smash (d['evidence'], r, 'Evidence__c')


def get_auth_token(url, params):
    r = requests.post(url, data=params)
    if r.status_code != 200:
        print('%s returns status code %d!' % (
            r.url, r.status_code), file=sys.stderr)
        return None
    #print(json.dumps(r.json(), indent=2))
    return r.json()['access_token']

def parse_config(file):
    with open(file) as f:
        config = json.load(f)
        if 'api' not in config or 'params' not in config:
            print('** %s: not a valid config file! **' % file, file=sys.stderr)
            sys.exit(1)
        return config

def load_objects(url, data, path, prefix):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer %s' % TOKEN
    }
    total = 0
    batch = 1
    for d in data:
        r = requests.patch(url, headers=headers, json=d)
        with open(path+'/%s_%05d.json' % (prefix, batch), 'w') as f:
            resp = {
                'status': r.status_code,
                'input': d,
                'response': r.json()
            }
            print (json.dumps(resp, indent=2), file=f)
        batch = batch + 1
        if 200 == r.status_code:
            total = total + len(d['records'])
        print('%d - %d' % (r.status_code, total))
    print ('%d record(s) loaded for %s' % (total, url))
    return total

def load_genes(file, out):
    with open(file, 'r') as f:
        data = json.load(f)
        load_objects(API['gene'], data, out, 'gene')

def load_phenotypes(file, out):
    with open(file, 'r') as f:
        data = json.load(f)
        load_objects(API['phenotype'], data, out, 'phenotype')

def load_drugs(file, out):
    with open(file, 'r') as f:
        data = json.load(f)
        load_objects(API['drug'], data, out, 'drug')

def load_disease(d, path='.'):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer %s' % TOKEN
    }
    term = d['term']
    term['Id'] = LUT[term['curie']]
    r = requests.post(API['disease'], headers=headers, json=d)

    base = path+'/'+term['curie'].replace(':', '_')
    sf = r.json()
    with open(base+'_sf.json', 'w') as f:
        print (json.dumps(sf, indent=2), file=f)
    with open(base+'_%d.json' % r.status_code, 'w') as f:
        if r.status_code == 200:
            smash(d, sf)
        print (json.dumps(d, indent=2), file=f)
        
    return (r.status_code, term['curie'], term['Id'])

def reload_disease(file):
    with open(file, 'r') as f:
        data = json.load(f)
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % TOKEN
        }
        r = requests.post(API['disease'], headers=headers, json=data)
        print ('%s -- %d' % (file, r.status_code))
        print (json.dumps(r.json(), indent=2))

    
def load_diseases(file, out, **kwargs):
    with open(file, 'r') as f:
        curies = {}
        if 'include' in kwargs and kwargs['include'] != None:
            for c in kwargs['include']:
                curies[c] = None
        start = 0
        if 'skip' in kwargs and kwargs['skip'] != None:
            start = kwargs['skip']
        data = json.load(f)
        total = 0
        count = 0
        if isinstance(data, list):
            for d in data:
                if ((len(curies) == 0 or d['term']['curie'] in curies)
                    and (start == 0 or count > start)):
                    r = load_disease(d, out)
                    print('%d -- %d/%s %s %s' % (r[0], total, count, r[1], r[2]))
                    if 200 == r[0]:
                        total = total + 1
                count = count + 1
            print('-- %d total record(s) loaded!' % total)
        else:
            load_disease(data, out)

def patch_objects1(target, source, field, *fields):
    if field in source:
        sfids = {}
        for s in source[field]:
            sfids[s['curie']] = s
        for t in target[field]:
            if t['curie'] in sfids:
                d = sfids[t['curie']]
                t['Id'] = d['Id']
                for f in fields:
                    t[f] = d[f]
        
def patch_objects2(target, source, field):
    if field in source:
        sfids = {}        
        for s in source[field]:
            if s['curie'] in sfids:
                sfids[s['curie']][s['label']] = s['Id']
            else:
                sfids[s['curie']] = {s['label']: s['Id']}
        patches = []
        processed = {}
        for t in target[field]:
            if t['curie'] in sfids and t['label'] in sfids[t['curie']]:
                id = sfids[t['curie']][t['label']]
                if id not in processed:
                    t['Id'] = id
                    processed[id] = None
                    patches.append(t)
            else:
                patches.append(t)
            
        if len(patches) > 0:
            target[field] = patches
            
def patch_evidence(target, source):
    sfids = {}
    for e in source['evidence']:
        sfids[e['url']] = e['Id']
    for e in target['evidence']:
        if e['url'] in sfids:
            e['Id'] = sfids[e['url']]

def patch_objects(target, source, field, minlen=0):
    if field in source and field in target:
        patches = []
        processed = {}
        for t in target[field]:
            best_s = {}
            ovbest = {}
        
            t['Id'] = ''
            for s in source[field]:
                ov = {k: t[k] for k in t if k in s and s[k] == t[k]}
                if len(ov) > len(ovbest):
                    best_s = s
                    ovbest = ov
            if len(ovbest) > minlen:
                t['Id'] = best_s['Id']
                if t['Id'] not in processed:
                    patches.append(t)
                    processed[t['Id']] = None
            else:
                patches.append(t)
            
        if len(patches) > 0:
            target[field] = patches
            
    elif field in source:
        # deleted field
        print("** target object doesn't have field '%s'; "
              "deletion is currently not supported!" % field, file=sys.stderr)
    
def patch_disease(disease, in_dir, out_dir):
    file = in_dir+'/%s_200.json' % disease['term']['curie'].replace(':','_')
    r = ()
    if os.access(file, os.R_OK):
        with open(file, 'r') as f:
            d = json.load(f)
            #print(json.dumps(d, indent=2))
            disease['term']['Id'] = d['term']['Id']
            patch_objects2 (disease, d, 'disease_categories')
            patch_objects2 (disease, d, 'synonyms')
            patch_objects (disease, d, 'external_identifiers', 2)
            patch_objects2 (disease, d, 'inheritance')
            patch_objects2 (disease, d, 'age_at_onset')
            patch_objects2 (disease, d, 'age_at_death')
            patch_objects (disease, d, 'diagnosis', 1)
            patch_objects (disease, d, 'epidemiology')
            patch_objects1 (disease, d, 'genes', 'gene_sfdc_id')
            patch_objects1 (disease, d, 'phenotypes', 'phenotype_sfdc_id')
            patch_objects1 (disease, d, 'drugs', 'drug_sfdc_id')
            patch_evidence (disease, d)
            #print(json.dumps(disease, indent=2))
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer %s' % TOKEN
            }
            r = requests.post(API['disease'], headers=headers, json=disease)
            file = (out_dir+'/'+disease['term']['curie'].replace(':','_')+'_%d'
                    % r.status_code)
            sf = r.json()
            with open(file+'_sf.json', 'w') as f:
                print (json.dumps(sf, indent=2), file=f)
            print('%d...patching %s' % (r.status_code, disease['term']['curie']))
            with open(file+'.json', 'w') as f:
                if 200 == r.status_code:
                    smash(disease, sf)
                print (json.dumps(disease, indent=2), file=f)
    else:
        r = load_disease(disease, out_dir)
    return r

def patch_diseases(file, in_dir, out_dir, include):
    with open(file, 'r') as f:
        curies = {}
        if include != None:
            for c in include:
                curies[c] = None
        data = json.load(f)
        if isinstance(data, list):
            for d in data:
                if len(curies) == 0 or d['term']['curie'] in curies:
                    patch_disease(d, in_dir, out_dir)
        else:
            patch_disease(data, in_dir, out_dir)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', required=True,
                        help='Required configuration in json format')
    parser.add_argument('-t', '--type', required=True,
                        choices=['gene', 'phenotype', 'disease', 'drug'],
                        help='Input file is of specific type')
    parser.add_argument('-r', '--reload', help='Reload disease file',
                        action='store_true')
    parser.add_argument('-i', '--include', dest='curies', default='',
                        nargs='+', help='Include only those curies specified')
    parser.add_argument('-q', '--input', help='Path to previously loaded files')
    parser.add_argument('-p', '--patch', help='Patch disease based on previously load files per the location specified by -q', action='store_true')
    parser.add_argument('-m', '--mapping', default='gard_diseases_sf.csv',
                        help='🙄 Salesforce disease mapping file (default: gard_diseases_sf.csv)')
    parser.add_argument('-s', '--skip', default=0, type=int,
                        help='Skip specified number of records in load')
    parser.add_argument('-o', '--output', default='.',
                        help='Output path (default .)')
    parser.add_argument('FILE', help='Input JSON file')
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()
    print('-- type: %s' % args.type)
    print('-- config: %s' % args.config)
    print('-- output: %s' % args.output)
    print('-- curies: %s' % args.curies)
    print('-- FILE: %s' % args.FILE)
    
    config = parse_config(args.config)
    API = config['api']
    TOKEN = get_auth_token(API['token'], config['params'])
    print('-- TOKEN: %s...' % TOKEN[0:32])
    
    try:
        os.makedirs(args.output)
    except FileExistsError:
        pass

    def load_mappings(lut, file):
        print('-- mapping: %s' % file)
        with open(file) as f:
            f.readline() # skip header
            for line in f.readlines():
                gard, sfid = line.strip().split(',')
                lut[gard] = sfid
            print('-- %d mappings loaded!' % (len(lut)))
        
    if args.type == 'disease':
        if args.reload:
            print('-- reloading...%s' % args.FILE)
            reload_disease(args.FILE)
        elif args.patch:
            load_mappings(LUT, args.mapping)            
            print('-- patching...%s, input=%s output=%s'
                  % (args.FILE, args.input, args.output))
            patch_diseases(args.FILE, args.input, args.output, args.curies)
        else:
            load_mappings(LUT, args.mapping)
            load_diseases(args.FILE, args.output,
                          include=args.curies, skip=args.skip)
        
    elif args.type == 'gene':
        load_genes(args.FILE, args.output)

    elif args.type == 'drug':
        load_drugs(args.FILE, args.output)

    elif args.type == 'phenotype':
        load_phenotypes(args.FILE, args.output)
