from __future__ import print_function, division
from pymongo import MongoClient
import urllib, urllib2, feedparser, re, json, os, tarfile, zipfile

root = 'www';
rss_feed = 'https://pypi.python.org/pypi?%3Aaction=rss'

class PyDigger(object):
	def __init__(self):
		mongo_client = MongoClient('localhost', 27017)
		mongo_db = mongo_client.pydigger
		self.packages = mongo_db.packages


	def get_json(self, link):
		#link   # http://pypi.python.org/pypi/getvps/0.1
		# check if link matches the format we are expecting:
		# http://pypi.python.org/pypi/<package>/<version>
		match = re.search(r'http://pypi.python.org/pypi/([^/]+)/([^/]+)$', link)
		if not match:
			print("ERROR: url {} does not match the expected format".format(link))
			return False
	
		package = match.group(1)
		version = match.group(2)
	
		data = self.packages.find_one({'package' : package, 'version' : version });
		if not data:
			data = {
				'package' : package,
				'version' : version,
				'status'  : 'waiting_for_zip_url'
			}
			print("LOG: adding package {} version {} to the database ".format(package, version))
			self.packages.insert(data)
			data = self.packages.find_one({'package' : package, 'version' : version });
	
		if not data:
			print("INERNAL ERROR: data just added and cannot be found? package {} version {}".format(package, version))
			return False

		self.data = data
		return True


	def run(self):
		w = urllib2.urlopen(rss_feed)
		rss = w.read()
		feed = feedparser.parse( rss )
		for v in feed['entries']:
			if not self.get_json(v['link']):
				return
	
			#if data and data['status'] != 'waiting':
			#	print("LOG: package {} version {} are already in the database".format(package, version))
			#	continue
	
			# It seems that a package might be already included in the RSS feed even before it was indexed by Pypi
			# and so it does not yet have the details in the 'releases' and in the 'urls'
			# we might need to take this in account when processing packages
			# or maybe if there are multiple version numbers in the 'releases' ?
	
			if 'zip_url' not in self.data:
				url = 'http://pypi.python.org/pypi/{}/{}/json'.format(self.data['package'], self.data['version'])
				w = urllib2.urlopen(url)
				json_string = w.read()
				#print(json_string)
				package_info = json.loads(json_string)
				try:
					zip_url = package_info['releases'][version][0]['url']
				except:
					print("LOG: zip_url missing from json for package {} version {}".format(self.data['package'], self.data['version']))
					continue
	
				self.data['zip_url'] = zip_url
				self.data['status']  = 'zip_url_found'
				print("LOG: zip_url {} found in json".format(self.data['zip_url']))
				self.packages.save(self.data)
	
			# remove the URL from the beginning of the zip_url and add it to the path to 'root'
			m = re.search(r'^https://pypi.python.org/(.*)', self.data['zip_url'])
			if not m:
				print("ERROR: zip_url prefix does not match {}".format(self.data['zip_url']))
				self.data['status'] = 'error_unknown_zip_url_prefis'
				self.packages.save(self.data)
				continue
	
			local_zip_file = root + '/' + m.group(1)
			local_path = os.path.dirname(local_zip_file);
			if not os.path.exists(local_zip_file):
				if not os.path.exists(local_path):
					print("LOG: creating dir {}".format(local_path))
					os.makedirs(local_path)
				print("LOG: downloading {} to {}".format(self.data['zip_url'], local_zip_file))
				urllib.urlretrieve(self.data['zip_url'], local_zip_file)
	
			m = re.search(r'(.*)(\.tar\.gz|\.zip)$', local_zip_file)
			if m:
				project_path = m.group(1)
				extension    = m.group(2)
				if not os.path.exists(project_path):
					print("LOG: unzipping {} to {} using {}".format(local_zip_file, local_path, extension))
					if extension == '.tar.gz':
						tar = tarfile.open(local_zip_file)
						tar.extractall(path=local_path)
						tar.close()
					elif extension == '.zip':
						tar = zipfile.ZipFile(local_zip_file)
						tar.extractall(path=local_path)
						tar.close()
					else:
						raise(Exception('Internal error. Unknown extension: {}'.format(extension)))
			else:
				print("ERROR: unknown zip file type {}".format(local_zip_file))
				continue
	
			# list all the files in the project_path and add it to the database
			if 'files' not in self.data:
				self.data['files'] = []
				for dirname, dirnames, filenames in os.walk(project_path):
					for filename in filenames:
						file_path = os.path.join(dirname, filename)[len(project_path)+1:]
						self.data['files'].append(file_path)
				self.packages.save(self.data)
	
	
		## fetch the rss feed
		## list the most recent package names and version numbers
		## fetch the json file of each package
	    ## http://pypi.python.org/pypi/<package_name>/<version>/json
		## add information to a database
		## download each package
		## unzip them
		# collect information about the package (list of files)
	
