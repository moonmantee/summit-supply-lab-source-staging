OLD=('SUMMIT-SHOP01-BASELINE-V1','SUM-101','SUM-102','SUM-103','Ridgeline daypack','Alpine insulated bottle','Trail first aid kit','$49.00','$24.00','$18.00')
NEW=OLD[1:7]+('$50.00','$24.00','$18.00')


def correct(data):
    import copy
    proposed=copy.deepcopy(data)
    services=[entry for entry in proposed.get('services',[]) if entry.get('id')=='shop01-https']
    if len(services)!=1 or services[0].get('probe')!='https': raise ValueError('Expected one shop01 HTTPS service')
    if services[0].get('expected') not in (list(OLD),list(NEW)): raise ValueError('Unknown existing storefront expectations')
    services[0]['expected']=list(NEW)
    return proposed
