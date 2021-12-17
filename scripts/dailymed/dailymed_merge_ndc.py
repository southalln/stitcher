import sys
import os
import io
import gzip
import zipfile
import pandas as pd
import urllib.request

def prepUniiDF():
    uniiZip = 'temp/UNIIs.zip'
    if not os.path.exists(uniiZip):
        with urllib.request.urlopen('https://fdasis.nlm.nih.gov/srs/download/srs/UNIIs.zip') as response:
            with open(uniiZip, 'wb') as out:
                out.write(response.read())
    with zipfile.ZipFile(uniiZip) as uniizip:
        with uniizip.open(uniizip.namelist()[1]) as uniifile:
            unii = pd.read_csv(uniifile, sep='\t', index_col='Name')
            unii['Locant Name'] = unii.index.copy(deep=True)
            unii.index = unii.index.str.replace(' \[.*\]$', '', regex=True)
    return unii

def prepNDCDF():
    ndcZip = 'temp/ndctext.zip'
    if not os.path.exists(ndcZip):
        with urllib.request.urlopen('https://www.accessdata.fda.gov/cder/ndctext.zip') as response:
            with open(ndcZip, 'wb') as out:
                out.write(response.read())
    with zipfile.ZipFile(ndcZip, 'r') as ndcZipRef:
        with ndcZipRef.open('product.txt') as ndcFile:
            ndc = pd.read_csv(ndcFile, sep="\t", error_bad_lines=False, encoding = "ISO-8859-1", na_filter=False, dtype=str)
            return ndc

def findUnii(uniiDF, name):
    if name in uniiDF.index:
        results = uniiDF.loc[[name]]
        try:
            if results is not None:
                if 'of' in results.TYPE.values:
                    results = results.loc[results['TYPE'] == 'of']
                return results.iat[0, 1]
        except:
            results = uniiDF.loc[name]
            print(name)
            print(results)
            print(results.shape)
            print("oops")
            sys.exit()
    return None

def getArchiveLabel(product, labelername, path = 'temp/labels/'):
    url = 'https://dailymed.nlm.nih.gov/dailymed/archives/index.cfm?query='+urllib.parse.quote_plus(product)+'&date=&pagesize=20&page=1'
    with urllib.request.urlopen(url) as response:
        html = response.read()
        idx = html.find(b'<a href="/dailymed/archives/fdaDrugInfo.cfm?archiveid=')
        while idx > -1:
            ref = 'https://dailymed.nlm.nih.gov' + \
                  html[html.find(b'/dailymed', idx):html.find(b'" title="">', idx)].decode('utf-8')
            zip = 'https://dailymed.nlm.nih.gov/dailymed/getArchivalFile.cfm?archive_id=' + \
                  html[html.find(b'archiveid=', idx)+10:html.find(b'" title="">', idx)].decode('utf-8')
            prod = html[html.find(b'" title="">', idx)+11:html.find(b'<br></a>', idx)].decode('utf-8')
            labeler = html[html.find(b'Packager: <span>', idx)+16:html.find(b'</span></div>', idx)].decode('utf-8').replace('&amp;', '&')
            date = html[html.find(b'<div class="date">', idx)+18:html.find(b'<a download target="_blank"', idx)].decode('utf-8')
            print(ref, zip, prod, labeler, date)
            if labeler == labelername:
                with urllib.request.urlopen(zip) as response:
                    outfile = path + response.info().get_filename()
                    with open(outfile, 'wb') as out:
                        out.write(response.read())
                    return outfile
            idx = html.find(b'<a href="/dailymed/archives/fdaDrugInfo.cfm?archiveid=', idx+1)
    return None

def searchArchiveMissingNDCs(spl, ndc):
    spl_miss = ndc[~ndc.PRODUCTNDC.isin(list(set(spl.NDC)))]
    print(spl_miss.info(verbose=True))
    entryList = []
    for index, row in spl_miss.iterrows():
        unii = findUnii(uniiDF, row['NONPROPRIETARYNAME'].upper())
        if unii is None or unii not in spl.UNII.values:
            unii2 = findUnii(uniiDF, row['PROPRIETARYNAME'].upper()) if not pd.isna(row['PROPRIETARYNAME']) else None
            if unii2 is None or unii2 not in spl.UNII.values:
                unii3 = findUnii(uniiDF, row['SUBSTANCENAME'].upper()) if not pd.isna(row['SUBSTANCENAME']) else None
                if unii is None:
                    if unii2 is None:
                        unii = unii3
                    else:
                        unii = unii2
            else:
                unii = unii2

        print(index, unii, unii in spl.UNII.values)
        if unii is not None and unii not in spl.UNII.values and \
                row['APPLICATIONNUMBER'] not in spl.ApprovalAppId.values and \
                row['MARKETINGCATEGORYNAME'] not in ['UNAPPROVED HOMEOPATHIC']:
            print(row)
            archiveLabel = None #!!!! getArchiveLabel(row['PROPRIETARYNAME'], row['LABELERNAME'], 'temp/labels/')
            if archiveLabel is None: # couldn't find an SPL version of this product in the archive
                entry = {'UNII': unii, \
                         'MarketingStatus': row['MARKETINGCATEGORYNAME'], \
                         'ProductCategory': (row['PRODUCTTYPENAME'] + ' LABEL'), \
                         'MarketDate': row['STARTMARKETINGDATE'], \
                         'EndDate': row['ENDMARKETINGDATE'], \
                         'InitialYealApproval': str(row['STARTMARKETINGDATE'])[:4] if len(str(row['STARTMARKETINGDATE'])) > 4 else '', \
                         'ApprovalAppId': row['APPLICATIONNUMBER'], \
                         'Equiv NDC': '', \
                         'NDC': row['PRODUCTNDC'], \
                         'Route': row['ROUTENAME'], \
                         'ActiveMoietyName': row['NONPROPRIETARYNAME'], \
                         'GenericProductName': row['PROPRIETARYNAME'], \
                         'Product': row['PROPRIETARYNAME'], \
                         'Sponsor': row['LABELERNAME'], \
                         'URL': 'https://www.google.com/search?q=NDC+' + row['PRODUCTNDC'], \
                         'Indications': '', \
                         'Comment': '', \
                         }
                if entry['EndDate'] == '' and row['NDC_EXCLUDE_FLAG'] == 'E': # Expired
                    entry['EndDate'] = row['LISTING_RECORD_CERTIFIED_THROUGH']
                print(entry)
                entryList.append(pd.Series(entry))
    newDF = pd.concat(entryList, axis=1).T
    print(len(spl.UNII.values))
    spl = pd.concat([spl, newDF], ignore_index=True)
    print(len(spl.UNII.values))

    # zip ../stitcher-rawinputs/files/spl-ndc/spl-missing-labels.zip temp/labels/*
    return spl

if __name__ == "__main__":
    # get latest UNII dictionary to resolve NDC substance names to UNIIs, which SPLs already have
    uniiDF = prepUniiDF()
    print(uniiDF.info(verbose=True))
    print(findUnii(uniiDF, 'SULFASYMAZINE'.upper()))

    # get SPLs from the FDA and use old SPLs if no longer available from dailymed dump
    fileTypes = ['rx', 'otc', 'ani', 'rem', 'missing'] #'homeo' homeopathic lables not used
    splDF = pd.concat([pd.read_csv('temp/spl_'+fileType+'.txt', sep="\t", error_bad_lines=False, na_filter=False, dtype=str) \
                       for fileType in fileTypes], ignore_index=True)
    for fileType in fileTypes:
        g_old = '../stitcher-rawinputs/files/spl-ndc/spl_'+fileType+'_old.txt.gz'
        f_old = gzip.open(g_old, 'rb')
        df_old = pd.read_csv(f_old, sep="\t", error_bad_lines=False, na_filter=False, dtype=str)
        df_diff = df_old[~df_old.NDC.isin(splDF.NDC.values)]
        splDF.append(pd.concat([splDF, df_diff], ignore_index=True))
    print(splDF.info(verbose=True))

    # get latest NDC file
    ndcDF = prepNDCDF()
    print(ndcDF.info(verbose=True))

    # get old NDC file to capture discontinued products
    ndcOldFileGZ = '../stitcher-rawinputs/files/spl-ndc/Products_all-2018-02-25.txt.gz' # from https://data.nber.org/fda/ndc/
    with gzip.open(ndcOldFileGZ, 'rb') as ndcOldFile:
        entryList = []
        ndcOldDF = pd.read_csv(ndcOldFile, sep="\t", error_bad_lines=False, encoding = "ISO-8859-1", na_filter=False, dtype=str)
        for index, entry in ndcOldDF[~ndcOldDF.PRODUCTNDC.isin(ndcDF.PRODUCTNDC.values)].iterrows():
            if entry.ENDMARKETINGDATE == '':
                entry.ENDMARKETINGDATE = entry.LISTING_RECORD_CERTIFIED_THROUGH
            entryList.append(entry)
        #print(len(entryList))
        newDF = pd.concat(entryList, axis=1).T
        #print(newDF.info(verbose=True))
        ndcDF = pd.concat([ndcDF, newDF], ignore_index=True)
        print(ndcDF.info(verbose=True))

    # convert extra NDCs to SPL-like entries and add to SPL dataframe
    splDF = searchArchiveMissingNDCs(splDF, ndcDF)

    # grab 5 examples of each substance
    summaryList = []
    for unii in splDF.UNII.unique():
        entries = []
        indicies = []
        uniiset = splDF[splDF.UNII == unii]
        print(unii, uniiset.shape[0])
        uniiset.sort_values(by=['MarketDate'], ascending=[True])
        for index, entry in uniiset.iterrows():
            if len(entries) < 2 and (entry.NDC not in indicies):
                entries.append(entry)
                indicies.append(entry.NDC)
        uniiset.sort_values(by=['EndDate'], ascending=[True])
        entry = uniiset.iloc[-1]
        if len(entries) < 3 and (entry.NDC not in indicies):
            entries.append(entry)
            indicies.append(entry.NDC)
        uniiset.sort_values(by=['ActiveCode', 'MarketingStatus', 'ApprovalAppId', 'MarketDate'], ascending=[True, False, True, True])
        for index, entry in uniiset.iterrows():
            if len(entries) < 6 and (entry.NDC not in indicies):
                entries.append(entry)
                indicies.append(entry.NDC)
        for entry in entries:
            summaryList.append(entry)

    # write out summary list
    summaryDF = pd.concat(summaryList, axis=1).T
    summaryDF.to_csv("data/spl_summary.txt", sep="\t", index=False, encoding="utf-8")

