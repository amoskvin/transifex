import os, commands
from django.conf import settings
from translations.lib.types import (TransManagerMixin, TransManagerError)
from translations.models import POFile, Language

import polib

class POTStatsError(Exception):

    def __init__(self, language):
        self.language = language

    def __str__(self):
        return "Could not calculate the statistics using the '%s' " \
               "language." % (self.language)

class POTManager(TransManagerMixin):
    """ A browser class for POT files. """

    def __init__(self, file_set, path, source_lang):
        self.file_set = file_set
        self.path = path
        self.source_lang = source_lang
        self.msgmerge_path = os.path.join(settings.MSGMERGE_DIR, 
                                     os.path.basename(self.path))

    def get_file_content(self, filename, isMsgmerged=False):
        if filename in self.file_set:
            if isMsgmerged:
                file_path = os.path.join(self.msgmerge_path, filename)
            else:
                file_path = os.path.join(self.path, filename)
            filef = file(file_path, 'rb')
            file_content = filef.read()
            filef.close()
            return file_content
        else:
            raise IOError("File not found.")
        
    def get_po_files(self):
        """ Return a list of PO filenames """

        po_files = []
        for filename in self.file_set:
            if filename.endswith('.po'):
                po_files.append(filename)
        po_files.sort()
        return po_files

    def get_langfile(self, lang):
        """ Return a PO filename """

        for filepath in self.get_po_files():
            if self.guess_language(filepath) == lang:
                return filepath

    def guess_language(self, filepath):
        """ Guess a language from a filepath """

        if 'LC_MESSAGES' in filepath:
            fp = filepath.split('LC_MESSAGES')
            return os.path.basename(fp[0][:-1:])
        else:
            return os.path.basename(filepath[:-3:])

    def get_langs(self):
        """ Return all langs tha have a po file for a object """

        langs = []
        for filepath in self.get_po_files():
            langs.append(self.guess_language(filepath))
        langs.sort()
        return langs

    def calcule_stats(self, lang):
        """ 
        Return the statistics of a specificy language for a 
        object 
        """
        try:
            (isMsgmerged, file_path) = self.msgmerge(self.get_langfile(lang),
                                                  self.get_source_file())
            po = polib.pofile(file_path)
            return {'trans': len(po.translated_entries()),
                    'fuzzy': len(po.fuzzy_entries()),
                    'untrans': len(po.untranslated_entries()),
                    'error': False,
                    'isMsgmerged': isMsgmerged}
        except IOError:
            return {'trans': 0,
                    'fuzzy': 0,
                    'untrans': 0,
                    'error': True,
                    'isMsgmerged': isMsgmerged}     

    def create_stats(self, lang, object):
        """Set the statistics of a specificy language for a object."""
        try:
            stats = self.calcule_stats(lang)
            f = self.get_langfile(lang)
            s = POFile.objects.get(object_id=object.id, filename=f)
        except POTStatsError:
            # TODO: It should probably be raised when a checkout of a 
            # module has a problem. Needs to decide what to do when it
            # happens
            pass
        except POFile.DoesNotExist:
            try:
                l = Language.objects.by_code_or_alias(code=lang)
            except Language.DoesNotExist:
                l = None
            s = POFile.objects.create(language=l, filename=f, 
                                           object=object)
        s.set_stats(trans=stats['trans'], fuzzy=stats['fuzzy'], 
                    untrans=stats['untrans'], error=stats['error'])
        s.isMsgmerged = stats['isMsgmerged']
        return s.save()

    def stats_for_lang_object(self, lang, object):
        """Return statistics for an object in a specific language."""
        try: 
            return POFile.objects.filter(language=lang, 
                                         object_id=object.id)[0]
        except IndexError:
            return None

    def get_stats(self, object):
        """ Return a list of statistics of languages for an object."""
        return POFile.objects.filter(
                   object_id=object.id
        ).order_by('-trans_perc')

    def delete_stats_for_object(self, object):
        """ Delete all lang statistics of an object."""
        POFile.objects.filter(object_id=object.id).delete()

    def get_source_file(self):
        """Return the source file (pot)"""
        for filename in self.file_set:
            if filename.endswith('.pot'):
                return filename

    def msgmerge(self, pofile, potfile):
        """
        Merge two files and save the output at the settings.MSGMERGE_DIR.
        In case that error, copy the source file (pofile) to the 
        destination without merging.
        """
        isMsgmerged = True
        outpo = os.path.join(self.msgmerge_path, pofile)
        pofile = os.path.join(self.path, pofile)

        if not os.path.exists(os.path.dirname(outpo)):
            os.makedirs(os.path.dirname(outpo))

        try:
        # TODO: Find a library to avoid call msgmerge by command
            command = "msgmerge -o %(outpo)s %(pofile)s %(potfile)s" % {
                    'outpo' : outpo,
                    'pofile' : pofile,
                    'potfile' : os.path.join(self.path, potfile),}
            
            (error, output) = commands.getstatusoutput(command)
        except:
            error = True

        if error:
            # TODO: Log this. output var can be used.
            isMsgmerged = False
            import shutil
            shutil.copyfile(pofile, outpo)

        return (isMsgmerged, outpo)
