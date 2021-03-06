#!/usr/bin/python

import os
import re
import zipfile
from eulxml import xmlmap
import shutil
from time import sleep, time
import logging
import magic
import ftpsettings
import ftplib

pubmed_zipd_files = []

# This is a class for the eulxml lib to pull the things values we need from the XML
class Front(xmlmap.XmlObject):
    title = xmlmap.StringField('front/article-meta/title-group/article-title')
    year = xmlmap.StringField('front/article-meta/pub-date/year')
    month = xmlmap.StringField('front/article-meta/pub-date/month')
    day = xmlmap.StringField('front/article-meta/pub-date/day')
    surnames = xmlmap.StringListField('front/article-meta/contrib-group/contrib/name/surname')
    givennames = xmlmap.StringListField('front/article-meta/contrib-group/contrib/name/given-names')
    name_position = xmlmap.StringListField('front/article-meta/contrib-group/contrib/xref/sup')
    email = xmlmap.StringField('front/article-meta/author-notes/corresp/email')
    send_to = xmlmap.StringField('front/article-meta/author-notes/corresp')
    volume = xmlmap.StringField('front/article-meta/volume')
    pubmed_article = xmlmap.StringField('front/article-meta/article-id[@pub-id-type="manuscript"]')

# Super simple function to convert numeric months to alpha months
def convert_to_month(num_month):
    alpha_month = ''
    if num_month == '01':
        alpha_month = 'January'
    elif num_month == '02':
        alpha_month = 'February'
    elif num_month == '03':
        alpha_month = 'March'
    elif num_month == '04':
        alpha_month = 'April'
    elif num_month == '05':
        alpha_month = 'May'
    elif num_month == '06':
        alpha_month = 'June'
    elif num_month == '07':
        alpha_month = 'July'
    elif num_month == '08':
        alpha_month = 'August'
    elif num_month == '09':
        alpha_month = 'September'
    elif num_month == '10':
        alpha_month = 'October'
    elif num_month == '11':
        alpha_month = 'November'
    elif num_month == '12':
        alpha_month = 'December'
    return alpha_month

# A function to send commands to our pymail script that uses the SES SMTP from AWS
def mail(name, email, volume, article_num, destination):
    top = ''
    bottom = ''
    subject = ''
    sender = 'mvision@emory.edu'
    cc = 'gagiima@emory.edu'

    # We decide which email to send based on the value of "destination" send from
    # the update function

    if 'galley' in destination:
        top = ''',
\nYour typeset galley is available at the following link. Please ensure that all figures and tables are present and associated with their correct legends. Please respond within 24 hours, otherwise we will assume all is well and proceed with publication.
ERRORS NOTED AFTER PUBLICATION CANNOT BE CORRECTED!\n
\thttp://www.molvis.org/molvis/galley/priv/'''

        bottom = '''\n\nBest regards,
The Editors of Molecular Vision'''

        subject = 'Molecular Vision galley proof notification'

    else:
        top = ''',\n
Congratulations!  Your article has been published in Molecular Vision.
You can see it at:\n
\thttp://www.molvis.org/molvis/'''

        bottom = '''\n
An announcement will be sent to the subscribers of Molecular Vision Announcements (MV-ANN).\n
Work funded by NIH, HHMI, Wellcome Trust, or MRC must be made available  in PubMed Central once it is published. Molecular Vision has already submitted your paper to PubMed Central and PubMed; it should appear in  those repositories within a few days. You do not need to do anything,  we have done all the work for you!\n
If your paper includes data that you released to GenBank or other databases, you should request that those databases add the citation information for your paper to the appropriate database entries. Sorry, we cannot do this for you!\n
Warmest Regards,
The Editors of Molecular Vision'''

        subject = 'Molecular Vision publication notification'

    msg = 'Dear %s%s%s/%s%s' % (name, top, volume, article_num, bottom)

    # This is where we concatenate the various arguments and send them to our generic mail sending script
    os.system('python /data/scripts/pymail.py --to \'' + email + '\' --cc \'' + cc + '\' --sender \'' + sender + '\' --subject \'' + subject + '\' --body \'' + msg + '\'')
    logging.info('Email sent to %s' % email)

# This is where the real magic happens
def update(path, file):
    names = ''
    volume = ''
    toc_update = ''
    tmp = '/tmp/'
    destination = ''

    # Set the destination for files based on which directioy in which the files were found
    if 'publish' in path:
        destination = '/dav/molvis/'
    elif 'galley' in path:
        destination = '/dav/molvis/galley/priv/'

    # Unzip the files to the tmp directory
    os.system('unzip -d %s %s%s' % (tmp, path, file))
    #os.system('unzip -d' + tmp + ' ' + path + file)
    # Remove the zip file
    os.remove(path + file)
    # This strips off the '.zip' from the filename to set what we will call the article number.
    # This value is used to create the link
    article_num = file[0:-4]
    # Make a list of all the files we just unzipped
    ext_files = os.listdir(tmp + article_num)
    # Iterate through that list and find the XML file
    for ext_file in ext_files:
        pubmed_article_num = ''
        if 'XML' in ext_file:
            # Load the XML file into the above EULXML class
            article_info = xmlmap.load_xmlobject_from_file('%s%s/%s' % (tmp, article_num, ext_file), xmlclass=Front)
            # Get the volume number from the XML file and prepend a 'v'
            volume = 'v' + article_info.volume
            # Clean up the value for the author we will email
            send_to = re.sub('Correspondence to: ', "", article_info.send_to)
            send_to = re.sub(',.*', "", send_to)
            send_to = send_to.encode('utf8')

            pubmed_article_num = 'a%s' % article_info.pubmed_article[-4:]
            # We have to interate through all the names of the authors and string them together
            # We start at zero and move through the list
            num = 0
            for name in article_info.surnames:
                names = names + article_info.givennames[num] + ' ' + name + ', '
                num = num + 1

            # I'm sure there is a better way to do this, but we just take the numeric month from the XML
            # and convert it to the alpha month using the function above
            alpha_month = convert_to_month(article_info.month)
            # Concatenate the HTML we will use to update the toc.html file.
            toc_update = '\n\t<p>\n\t\t<font size="4"><b>' + article_info.title + '</b></font><br />\n\t\t<font size="3">' + names[0:-2] + '<br />\n\t\tPublished: ' + article_info.day + ' ' + alpha_month + ' ' + article_info.year + ' [<a href="' + volume + '/' + article_num + '">Full Text</a>]</font>\n\t</p>'
            toc_update = toc_update.encode('utf8')

            # Send some values to the above mail function that will generate the email and send it to our
            # email script.
            if article_info.email:
                mail(send_to, article_info.email, volume, article_num, destination)
            else:
                logging.warning('No email address listed in XML file')

    # If the original zip file was found in the 'to-publish' folder, we need to update the toc.html
    # If the original zip files was in the 'to-galley' floder, we skip this.
    if 'publish' in path:
        toc = '/dav/molvis/toc.html'
        toc_bk = '/dav/molvis/toc.bk'
        # Remove the old backup of the TOC
        os.remove(toc_bk)
        # Move current toc.html to toc.bk
        shutil.move(toc, toc_bk)

        # Create new toc.html
        with open(toc, 'w') as out:
            # Read the backup TOC we just made, add the HTML we generated earlier and write it all to
            # the new toc.html
            for line in open(toc_bk):
                out.write(line.replace('<!--new-->', '<!--new-->' + toc_update))

        logging.info('TOC upadated with %s' % article_num)

	      # Make zip for PubMed
        pubmed_files = []
        for ext_file in ext_files:
            article_file = '%s%s/%s' % (tmp, article_num, ext_file)
            mime = magic.Magic(mime = True)
            mime_type = mime.from_file(article_file)

            # Get the PDFs
            if 'pdf' in str(mime_type).lower() and 'app' not in article_file.lower():
                pubmed_files.append(ext_file)

            # Get the images
            if 'image' in str(mime_type).lower():
                pubmed_files.append(ext_file)

            # Get appendices
            if 'app' in article_file.lower():
                pubmed_files.append(ext_file)

            # Get XML
            if '.xml' in article_file.lower():
                pubmed_files.append(ext_file)

        # Zip it up
        zip_file_name = 'mv-%s-1-%s.zip' % (volume, pubmed_article_num)
        zipf = zipfile.ZipFile('/%s/%s' % (tmp, zip_file_name), 'w')

        os.chdir('%s/%s' % (tmp, article_num))
        for pubmed_file in pubmed_files:
            zipf.write(pubmed_file)

        zipf.close()

        # FTP the zip to PubMed
        session = ftplib.FTP(ftpsettings.server, ftpsettings.user, ftpsettings.password)
        zip_file = open('%s%s' % (tmp, zip_file_name),'rb')
        session.storbinary('STOR %s' % (zip_file_name), zip_file)
        zip_file.close()
        logging.info('%s uploaded' % zip_file_name)
        session.quit()

        # Build a list of zip files uploaded for emeail to PubMed
        pubmed_zipd_files.append('%s.zip' % pubmed_article_num)


    # Make sure the destination/volume folder exists. If it doesn't we need to create it.
    if not os.path.isdir(destination + volume):
        os.system('mkdir ' + destination + volume)

    # Move the files from /tmp to the destination/volume_number/
    shutil.move('%s%s'  % (tmp, article_num), '%s%s/' % (destination, volume))
    #shutil.move(tmp + article_num, destination + volume + '/')

    # This finishs up the update.

######################################
##                                  ##
##      This is where the           ##
##      really starts working       ##
##                                  ##
######################################

# The cron job sends the standard out into a log file so we can track errors.
# This line allows us track the times of the runs.
os.system("echo '*************';echo `date`;echo '*************'")

# Set up logging
logging.basicConfig(filename='/data/logs/molvis.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# Check to see if the script is still running or failed to complete the last time it ran.
# We do this by createing a file /data/scripts/molvis-running
if os.path.isfile('/data/scripts/molvis-running'):
    #logging.warning('File /data/scripts/molvis-running exists.')
    #logging.warning('Previous run is either still running or failed. Exiting')
    exit()
else:
    # Create the molvis-running file
    os.system('touch /data/scripts/molvis-running')

# Check to see if the WebDAV folder is mounted. If not, mount it.
if not os.path.ismount('/dav'):
    os.system('/usr/sbin/mount.davfs https://files.web.emory.edu/site/www.molvis.org/htdocs/ /dav')
    #logging.info('Mounting DAV')
    sleep(10)
    if not os.path.ismount('/dav'):
        logging.error('Mounting dav failed.')
        os.remove('/data/scripts/molvis-running')
        exit()
#else:
        #logging.warning('DAV already mounted')

# Let's make sure the /tmp directory is clear so everything unzips as it should
os.system("rm -rf /tmp/*")

# Check the to-publish and to-galley folders for new zip files
paths = ['/dav/to-publish/', '/dav/to-galley/']
for path in paths:
    files = os.listdir(path)
    # Sort the files so we process them in the correct order
    files.sort()
    for file in files:
        if 'zip' in file.lower():
            logging.info('%s found in %s' % (file, path))
            # We check to see if the file hasn't chenged in the past five minutes (300 seconds).
            # If it is newer, the concern is that it is not done uploading. If it is too new
            # we just skip it and check it next time.
            st = os.stat(path + file)
            mtime = st.st_mtime
            if (time() - mtime) > 300:
                # If the file is old enough, we send it on up to the above update function
                update(path, file)
                # Takes a break to give enough time to process everything before moving to the next file
                sleep(10)
            else:
                logging.info(file + ' found but not old enough')


# Here is where we will have to email PubMed
# pmc@ncbi.nlm.nih.gov

# Remove the molvis-running file
os.remove('/data/scripts/molvis-running')

# Unmount the WebDAV folder
os.system('umount /dav')
#if not os.path.ismount('/dav'):
    #logging.info('DAV unmounted')
#elif os.path.ismount('/dav'):
    #logging.warning('DAV failed to unmount')
