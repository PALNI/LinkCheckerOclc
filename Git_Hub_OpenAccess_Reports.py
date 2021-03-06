## The following code queries OCLC's Knowledge Base API for a particular collection (using the collection ID) and sends a report (Kbart as attachment) by email of all the broken links.
## This code has been designed to check Open Access collections.
## 2018-07-06 Clara Turp, for McGill University Library.


import csv
import json
import re
import requests
import urllib3
import urllib.request
import codecs
import smtplib
from email.message import Message
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from argparse import ArgumentParser


###################
#    Functions
###################

#KB API Functions
def queryBuilder(collectionName):

    parameters = "&link@rel=enclosure"
    myKey = "wskey=" + config['wskey']
    myQuery = "https://worldcat.org/webservices/kb/rest/collections/" + collectionName + myKey + parameters

    return myQuery


def callQuery(myUrl):
    response = requests.get(myUrl)
    xmlOutput = response.content.decode("utf-8")

    return xmlOutput

#Find, download and read Kbart
def matchKbartFilePattern(xmlOutput):

    kbartUrl = re.findall('<link\shref=\"([^\s]*_kbart.txt)\"\srel="enclosure"\stype="text\/csv;\scharset=UTF-8\"\stitle=\"kbart\sfile\"\slength=\".*\"\s\/>', xmlOutput)

    return kbartUrl


def kbartDownloadUrl(kbartUrl):

    myUrl = kbartUrl +"?"
    myKey = "wskey=" + config['wskey']
    myKbartUrl = myUrl + myKey

    return myKbartUrl

def kbartReader(myUrl):

    urlOutput = urllib.request.urlopen(myUrl)
    csvfile = csv.reader(codecs.iterdecode(urlOutput, 'utf-8'))

    return csvfile

#String cleaners
def lineCleaner(line):

    lineArray = []
    line = "".join(line)
    lineArray = line.split("\t")

    return lineArray

def stringCleaner(string):

    string = string.rstrip("\n")
    string = string.strip()

    return string

#Link checker
def testUrl(currentUrl):

    status = ""
    try:
        r = requests.get(currentUrl, timeout = 30 )
        code = r.status_code
        newUrl = r.url
        if code == 404:
            status = "error"
        elif code == 400:
            status = "error"
        else:
            try:
                matchFound = re.match(newUrl, currentUrl)
                currentUrlWithSlash = currentUrl + "/"
                matchCurrentUrlWithSlash = re.match(newUrl, currentUrlWithSlash)
                newUrlWithSlash = newUrl + "/"
                matchNewUrlWithSlash = re.match(newUrlWithSlash, currentUrlWithSlash) # A's best guess what is supposed to be here, since `line` doesn't make any sense.
                if matchFound:
                    status = "ok"
                elif matchCurrentUrlWithSlash:
                    status = "ok"
                elif matchNewUrlWithSlash:
                    status = "ok"
                else:
                    status = "redirects"
            except re.error:
                status = "redirects"

    except requests.exceptions.RequestException:
        status = "error"

    except urllib3.exceptions.LocationValueError:
        status = "error"

    except UnicodeError:
        status = "error"

    return status

def statusSorting(status, currentLine, currentUrl, errorFoundArray, redirectsArray):

    if status == "error":
        errorFoundArray.append(currentLine)
    elif status == "redirects":
        if not re.match("^(https|http)://doi.org", currentUrl):
            r = requests.get(currentUrl, timeout = 30 )
            newUrl = r.url
            currentLine[9] = newUrl
            redirectsArray.append(currentLine)

#Print in file
def printFile(myArray, filename):

    myPrintFile = open(filename, "w", newline = "", encoding="utf-8", errors= "ignore")
    writerFile = csv.writer(myPrintFile)
    for line in myArray:
        writerFile.writerow(line)

#Send emails

# The following two email functions have been adapted from a code shared by Rob (user:8747) on stack overflow.
# https://stackoverflow.com/questions/41469952/sending-an-email-via-the-python-email-library-throws-error-expected-string-or-b

def email(fromEmail, toEmail, filename, message):

    msg = MIMEMultipart()
    msg['Subject'] = 'Report| Problematic links in Open Access Collection'
    msg['From'] = fromEmail['email']
    msg['To'] = toEmail['email']

    body = MIMEText(message)
    msg.attach(body)

    with open(filename) as fp:
        record = MIMEText(fp.read())
        record['Content-Disposition'] = 'attachment; filename=' + filename
        msg.attach(record)

    server = smtplib.SMTP(fromEmail['server']['address'], fromEmail['server']['port'])
    server.ehlo()
    server.starttls()
    server.login(fromEmail['email'], fromEmail['server']['password'])
    server.sendmail(fromEmail['email'], toEmail['email'], msg.as_string())
    server.quit()


def noReportsEmail(fromEmail, toEmail, message):

    msg = MIMEMultipart()
    msg['Subject'] = 'Report| Problematic links in Open Access Collection'
    msg['From'] = fromEmail['email']
    msg['To'] = toEmail['email']

    body = MIMEText(message)
    msg.attach(body)

    server = smtplib.SMTP(fromEmail['server']['address'], fromEmail['server']['port'])
    server.ehlo()
    server.starttls()
    server.login(fromEmail['email'], fromEmail['server']['password'])
    server.sendmail(fromEmail['email'], toEmail['email'], msg.as_string())
    server.quit()


###################
#    Main Code
###################

# Read in command line arguments.
parser = ArgumentParser(description="This program queries OCLC's Knowledge Base API for a particular collection (using the collection ID) or parses a local KBART file and sends a report (KBART as attachment) by email of all the redirecting and broken links. This program has been designed to check Open Access collections.", epilog="If both a config file and optional parameters are defined, the config file values will be overwritten by the optional parameters which are defined.")

parser.add_argument('-c', '--config', dest='config', metavar='config', default='config.json')
parser.add_argument('-d', '--debug', action='store_const', const=True, dest='debug', metavar='debug', default=False)
parser.add_argument('-w', '--wskey', dest='wskey', metavar='wskey')
parser.add_argument('-k', '--kbcollections', dest='collections', metavar='collections', nargs='+', help="The OCLC KB collection identifiers of collections to scan.")
parser.add_argument('-l', '--local', '--localcollections', dest='localcollections', metavar='localcollections', nargs='+', help="The names of local KBART files for collections to scan.")
parser.add_argument('-f', '--from', dest='fromEmail', metavar='fromEmail')
parser.add_argument('-t', '--to', dest='toEmail', metavar='toEmail')
parser.add_argument('-s', '--server', '--emailserver', dest='server', metavar='server', nargs=3, help="The address, port, and password (used with the 'fromEmail' account) of the server from which to send email.")

arguments = parser.parse_args()

try:
    with open(arguments.config, 'r', encoding='utf-8') as configFile:
        config = json.load(configFile)
except FileNotFoundError as err:
    with open('config_template.json', 'r', encoding='utf-8') as configFile:
        config = json.load(configFile)

# arguments.debug is always set. There is no way to turn off debug if it is set in the config file.
if arguments.debug:
    config['debug'] = True

# If optional arguments were submitted, overwrite the values in the config file.
if arguments.wskey is not None:
    config['wskey'] = arguments.wskey

if arguments.collections is not None:
    config['collections'] = arguments.collections

if arguments.localcollections is not None:
    config['localcollections'] = arguments.localcollections

if arguments.fromEmail is not None:
    config['email']['from']['email'] = arguments.fromEmail

if arguments.toEmail is not None:
    config['email']['to']['email'] = arguments.toEmail

if arguments.server is not None:
    config['email']['from']['server']['address'] = arguments.server[0]
    config['email']['from']['server']['port'] = arguments.server[1]
    config['email']['from']['server']['password'] = arguments.server[2]

# Get ready to process the collections.
collectionsArray = config['collections']
localCollectionsArray = config['localcollections']

kbartUrlArray = []

for collection in collectionsArray:
    myUrl = queryBuilder(collection + "?")
    xmlOutput = callQuery(myUrl)
    myKbartUrl = matchKbartFilePattern(xmlOutput)
    kbartUrlArray.append((collection, kbartDownloadUrl(myKbartUrl[0])))

for collection in localCollectionsArray:
    kbartUrlArray.append((collection, 'file:' + urllib.request.pathname2url(collection)))

if (config['debug']):
    print(kbartUrlArray)

for collection in kbartUrlArray:

    errorFoundArray = []
    redirectsArray = []

    csvfile = kbartReader(collection[1])

    count = 0

    for line in csvfile:
        cleanedLineArray = lineCleaner(line)

        if cleanedLineArray[0] != "publication_title":
            cleanedCurrentUrl = stringCleaner(cleanedLineArray[9])
            urlStatus = testUrl(cleanedCurrentUrl)
            statusSorting(urlStatus, cleanedLineArray, cleanedCurrentUrl, errorFoundArray, redirectsArray)

        count = count + 1

        if (config['debug']):
            print('Checked line ' + str(count) + '.')

            if (count > 10):
                break

    if len(redirectsArray) > 0:
        printFileName = "openAccess_redirects_results_" + collection[0] + ".csv"
        message = "Report of redirecting links in collection " + collection[0] + ". The links have been corrected in the attached file."

        printFile(redirectsArray, printFileName)
        email(config['email']['from'], config['email']['to'], printFileName, message)

    if len(errorFoundArray) > 0:
        printFileName = "openAccess_errors_results_" + collection[0] + ".csv"
        message = "Report of broken links in collection " + collection[0] + "."

        printFile(errorFoundArray, printFileName)
        email(config['email']['from'], config['email']['to'], printFileName, message)

    elif len(errorFoundArray) == 0 and len(redirectsArray) == 0:
        message = "No broken or redirecting links were found in collection: " + collection[0] + "."

        noReportsEmail(config['email']['from'], config['email']['to'], message)
