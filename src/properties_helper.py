#!/usr/bin/env python3

import glob
import yaml
import os
import datetime as dt
import subprocess
import shlex
#import jack
import re
from pathlib import Path
import traceback
import threading
import time

_instance = None

class GroupPropertiesHelper:


  def __init__(self, Debug=True):
    self.Debug = Debug
    if self.Debug:
      print('<==== GroupPropertiesHelper:: init')

    self.sched = None
    self.session_path_by_port = {}
    self.jackclients = {}
    self.layer_list = []
    self.lock = threading.Lock()            
    self.executing = False
    self.read_sessions()
    self.stopEvent = threading.Event()
    self.thread = threading.Thread(target=self.run)
    self.thread.start()
    
    if self.Debug:
      print('>==== GroupPropertiesHelper:: init')
  
  def run(self):
    while not self.stopEvent.wait(5):
      self.read_sessions()
      
  @staticmethod
  def instance():
    global _instance
    if not _instance:
      _instance = GroupPropertiesHelper()      
    return _instance

  def stop(self):
    if self.Debug:
      print ('GroupPropertiesHelper:: stop')
    self.stopEvent.set()
  
  def read_sessions(self):
    if not self.executing:
      self.executing = True
      try:
        if self.Debug:
          print ('<==== GroupPropertiesHelper:: read_sessions')
        portsToRemove = []
        for port in self.session_path_by_port:
          portsToRemove.append(port)
        
        ports = self.get_list_daemons()
        if ports:
          for port in ports:
            if port.isdigit():
              session_path = self.get_session_path(port)
                
              if port not in self.session_path_by_port:
                if session_path:
                  self.session_path_by_port[port] = session_path
                  self.updateProperties(port)
                  if port in portsToRemove:
                    portsToRemove.remove(port)
              elif self.session_path_by_port[port] != session_path:
                if session_path:
                  self.removeProperties(port)
                  self.session_path_by_port[port] = session_path
                  self.updateProperties(port)
                  if port in portsToRemove:
                    portsToRemove.remove(port)
              elif self.session_path_by_port[port] == session_path:
                if port in portsToRemove:
                  portsToRemove.remove(port)

        for port in portsToRemove:
          self.removeProperties(port)

        for port in portsToRemove:
          del self.session_path_by_port[port]

      except Exception as e:
        if self.Debug:
          traceback.print_exc()
          print (e)
      
      self.executing = False
    if self.Debug:
      print ('>==== GroupPropertiesHelper:: read_sessions')
            
  def get_list_clients(self, port):
    cmd = ['ray_control','--port', str(port), 'list_clients']
    if self.Debug:
      print(' '.join(cmd))
    try:
      out = subprocess.check_output(' '.join(cmd), shell=True, text=True)        
      if out.strip() == '':
        return None
      else:
        result = out.splitlines()
        return result
    except Exception as e:
      if self.Debug:
        traceback.print_exc()
        print (e)
      return None

  def get_custom_data(self, port, clientid, dataname, listtype=False, seperator="|"):
    cmd = ['ray_control','--port', str(port), 'client', '"' + clientid + '"', 'get_custom_data', dataname]
    if self.Debug:
      print(' '.join(cmd))
    try:
      out = subprocess.check_output(' '.join(cmd), shell=True, text=True)        
      result = out.splitlines()[0]
      if listtype:
        return result.split(seperator)
      return result
    except Exception as e:
      if self.Debug:
        traceback.print_exc()
        print (e)
      return None
    
  def get_session_path(self, port):
    try:
      sessionpath = subprocess.check_output(['ray_control', '--port', str(port), 'get_session_path'], text=True)
      if sessionpath.strip() == '':
        return None
      else:
        return sessionpath.strip()
    except Exception as e:
      if self.Debug:
        traceback.print_exc()
        print (e)
      return None

  def get_list_daemons(self):
    try:
      ports = subprocess.check_output(['ray_control', 'list_daemons'], text=True)
      listport = ports.split()
      if self.Debug:
        print (listport)
      return listport
    except Exception as e:
      if self.Debug:
        traceback.print_exc()
        print (e)
      return None

  def get_session_name(self, port):
    session_path = self.session_path_by_port[port]
    return os.path.basename(os.path.normpath(session_path))
  
  def removeProperties(self, port):
    if self.Debug:
      print ('<==== GroupPropertiesHelper:: removeProperties port: %s' % port)

    listToRemove = []
    for jackname in self.jackclients:
      if self.jackclients[jackname]['port'] == port:
        listToRemove.append(jackname)

    self.lock.acquire()
    for jackname in listToRemove:
      del self.jackclients[jackname]
    self.lock.release()

  def updateProperties(self,port):
    if self.Debug:
      print ('<==== GroupPropertiesHelper:: updateProperties')
      print ('update properties for port %s session_path %s' % (str(port), self.session_path_by_port[port]))
    
    clientids = self.get_list_clients(port)
    sessionname = self.get_session_name(port)

    jackclients = {}
    if clientids:
      for clientid in clientids:
        jacknames = self.get_custom_data(port, clientid, 'jacknames', seperator=';', listtype=True)
        if jacknames:
          layer = self.get_custom_data(port, clientid, 'layer')
          with_gui = self.get_custom_data(port, clientid, 'with_gui')
          windowtitle = self.get_custom_data(port, clientid, 'windowtitle')
          guitoload = self.get_custom_data(port, clientid, 'guitoload')
          clienttype = self.get_custom_data(port, clientid, 'clienttype')
        
          for jackname in jacknames:
            jackclients[jackname] = {
              'name' : jackname,
              'windowtitle' : windowtitle,
              'layer' : layer,
              'guitoload' : guitoload,
              'sessionname' : sessionname,
              'clientid' : clientid,
              'port': port,
              'clienttype' : clienttype,
              'with_gui' : with_gui
            }
    
    if self.Debug:
      print ('Updating ...')
    
    self.lock.acquire()

    for name in jackclients:
      if name not in self.jackclients:
        self.jackclients[name] = jackclients[name]

    if self.Debug:
      print (self.jackclients)
    self.lock.release()

    if self.Debug:
      print ('>==== GroupPropertiesHelper:: updateProperties')

  #def checkRaySessionPort(self, sessionname, port):
    #cmd = ['ray_control','--port', str(port), 'get_session_path']
    #if self.Debug:
      #print(' '.join(cmd))
    #out = subprocess.check_output(' '.join(cmd), shell=True, text=True)        
    #result = out.splitlines()[0]
    #return result.endswith(sessionname)
  
  def __getPidFromRayControl(self, jackclientname):
    
    if jackclientname not in self.jackclients:
      if self.Debug:
        print ('jackclientname not registered in properties: %s' % jackclientname)
      return 0
    
    port = self.jackclients[jackclientname]['port']
    sessionname = self.jackclients[jackclientname]['sessionname']
    clientid = self.jackclients[jackclientname]['clientid']
    clienttype = self.jackclients[jackclientname]['clienttype']
    
    pid = 0
    if clientid and port and clienttype:
      cmd = ['ray_control','--port', str(port), 'client', '"' + clientid + '"', 'get_pid']
      if self.Debug:
        print(' '.join(cmd))
      try:
        out = subprocess.check_output(' '.join(cmd), shell=True, text=True)        
        result = out.splitlines()[0]
        pid = int(result)
        if self.Debug:
          print ('ray pid: %d' % pid)
      except Exception as e:
        print (e)
        pid = 0
      if pid != 0 and (clienttype == 'proxy' or clienttype == 'proxy-wrapper'):
        try:
          cmd = ['pgrep','-P', str(pid)]
          out = subprocess.check_output(' '.join(cmd), shell=True, text=True)        
          result = out.splitlines()[0].split()
          pid = int(result[0])
          if self.Debug:
            print ('proxy child pid: %d' % pid)
          if clienttype == 'proxy-wrapper':
            cmd = ['pgrep','-P', str(pid)]
            out = subprocess.check_output(' '.join(cmd), shell=True, text=True)        
            result = out.splitlines()[0].split()
            pid = int(result[0])
            if self.Debug:
              print ('wrapper child pid: %d' % pid)
        except:
          print (e)
          pid = 0
    
    if self.Debug:
      print ('final pid: %d' % pid)
    return pid

  #def __getPidFromFile(self, jackclientname):
    
    #if jackclientname not in self.jackclients:
      #if self.Debug:
        #print ('jackclientname not registered in properties: %s' % jackclientname)
      #return 0
    
    #sessionname = self.jackclients[jackclientname]['sessionname']
    #clientid = self.jackclients[jackclientname]['clientid']
    
    
    #if sessionname and clientid:
      #try:
        #with open(self._dir + os.sep + sessionname + '.' + clientid + '.pid') as f:
          #pid = int(f.read().strip())
          #return pid
      #except Exception as e:
        #print (e)
        #pass
    #return 0

  #def updateSessionClosed(self, _file):
    #if self.Debug:
      #print ('<==== GroupPropertiesHelper:: updateSessionClosed')
    #with open(_file) as f:
      #values = os.path.basename(_file).split(".")
      #sessionname = values[0]
      #print ("sessionname:" + sessionname)
      #self.lock.acquire()
      #jackclienttoremove = []
      #for jackclientname in self.jackclients:
        #jackclient = self.jackclients[jackclientname]
        #if jackclient['sessionname'] == sessionname:
          #jackclienttoremove.append(jackclientname)
          #if self.Debug:
            #print ('%s removed.' % jackclientname)
      
      #for jackclientname in jackclienttoremove:
        #del self.jackclients[jackclientname]

      #self.lock.release()
      #try:
        #os.remove(_file)
      #except Exception as e:
        #print (e)
        #print('error during file remove %s' % pathfile)
        
      #fileList = glob.glob(self._dir + os.sep + sessionname + '.*.pid', recursive=False)
      #for pathfile in fileList:
        #try:
          #os.remove(pathfile)
        #except Exception as e:
          #print (e)
          #print('error during file remove %s' % pathfile)
          
        #if self.Debug:
          #print ('  remove %s' % pathfile)
          
      #if self.Debug:
        #print (self.jackclients)
    #if self.Debug:
      #print ('>==== GroupPropertiesHelper:: updateSessionClosed')
    

      
  def getProperty(self, jackclientname, propertyname):
    self.lock.acquire()
    result = self.get_property_unlock(jackclientname, propertyname)
    self.lock.release()
    return result
  
  def get_property_unlock(self, jackclientname, propertyname):
    # if the string ends with a number, its perhaps a pid number
    candidatepid = 0
    m = re.search(r'(\d+)$', jackclientname)
    if m:
      candidatepid = int(m.group(0))
      nametosearch = jackclientname.replace(str(candidatepid),'xxx-PID-xxx')
      if nametosearch in self.jackclients:
        jackclientname = nametosearch
        
    if propertyname == 'pid':
      # try to get pid from jacklib
      #result = jack.client_pid(jackclientname)
      # otherwise we get pid from pid Ray Control or from file
      #if result == 0:
      result = self.__getPidFromRayControl(jackclientname)
      #if result == 0:
        #result = self.__getPidFromFile(jackclientname)
      result = int(result)
      if self.Debug:
        print ('%s: %d (candidatepid: %d)' % (propertyname, result, candidatepid))
      return result
    
    result = None
    
    if jackclientname in self.jackclients and propertyname in self.jackclients[jackclientname]:
      result = self.jackclients[jackclientname][propertyname]
        
    if self.Debug:
      print ('%s: "%s"' % (propertyname, result))
    
    if result and result.strip() == '':
      result = None
    return result
  
  def getWinIdsAndtitlesFromPid(self, pid, option='--many-titles', regexp=None):
    menuoptions = []
    if 'title' not in option:
      raise Exception('Invalid option argument !')
    
    if pid != 0:
      args = []
      if regexp and regexp.strip() !='':
        args = [regexp]
        
      cmd = ['getwindidbypid', option, str(pid)] + args
      if self.Debug:
        print(' '.join(cmd))
      out = subprocess.check_output(' '.join(cmd), shell=True, text=True)        
      menuoptions = []
      for line in out.splitlines():
        fields = re.split(r'\s+', line.strip())
        if len(fields) > 4:
          winid = fields[0]
          title = " ".join(fields[4:])
          if title.strip() == '':
            title = None
          if fields[0] == 'None':
            winid = None
          if winid and title:
            menuoptions.append({'winid': winid, 'title': title})
    return menuoptions

  def getWinIdsAndtitlesFromRegexp(self, regexp, option='--many-titles'):
    menuoptions = []
    if 'title' not in option:
      raise Exception('Invalid option argument !')
    if regexp and regexp.strip() !='':
      cmd = ['getwindidbyregexp', option, '"' + regexp + '"']
      if self.Debug:
        print(' '.join(cmd))
      out = subprocess.check_output(' '.join(cmd), shell=True, text=True)        
      menuoptions = []
      for line in out.splitlines():
        fields = re.split(r'\s+', line.strip())
        if len(fields) > 3:
          winid = fields[0]
          title = " ".join(fields[3:])
          if title.strip() == '':
            title = None
          if fields[0] == 'None':
            winid = None
          if winid and title:
            menuoptions.append({'winid': winid, 'title': title})
    return menuoptions

    
  def getWinIdsAndtitles(self, jackclientname):
    if self.Debug:
      print ('<==== GroupPropertiesHelper:: getWinIdsAndtitles')
      print (jackclientname)
    
    windowtitle = None
    guitoload = None
    layer = None
    pid = None
    sessionname = None
    menuoptions = []


    try:
      self.lock.acquire()
            
      windowtitle = self.get_property_unlock(jackclientname,'windowtitle')
      guitoload = self.get_property_unlock(jackclientname,'guitoload')
      with_gui = self.get_property_unlock(jackclientname,'with_gui')
      layer = self.get_property_unlock(jackclientname,'layer')
      pid = self.get_property_unlock(jackclientname, 'pid')
      sessionname = self.get_property_unlock(jackclientname,'sessionname')      
      
      if self.Debug:
        print('--pid: %d\n--windowtitle:%s\n--guitoload:%s\n--layer:%s\n--sessionname:%s\nwith_gui:%s\n' % (pid,windowtitle,guitoload,layer,sessionname, str(with_gui)))
      
      if with_gui and pid != 0 and windowtitle:
        menuoptions = self.getWinIdsAndtitlesFromPid(pid, regexp=windowtitle)
      elif with_gui and pid != 0:
        menuoptions = self.getWinIdsAndtitlesFromPid(pid)
      elif not with_gui and windowtitle:
        menuoptions = self.getWinIdsAndtitlesFromRegexp(windowtitle)
    finally:
      self.lock.release()

    if len(menuoptions) == 0 and guitoload:
      menuoptions.append({'winid': None, 'title': 'start ' + guitoload})

    if sessionname:
      menuoptions += self.getWinIdsAndtitlesFromRegexp('RaySession - %s' % sessionname, option='--single-title')

      

    if self.Debug:
      print(menuoptions)
      print ('>==== GroupPropertiesHelper:: getWinIdsAndtitles')
    return menuoptions


  
  def loadOrSwitchToApp(self, jackclientname, winid):
    
    if self.Debug:
      print ('<==== GroupPropertiesHelper:: loadOrSwitchToApp')
      print ('winid: %s, jackclientname: %s' % (winid,jackclientname))
 
    windowtitle = None
    guitoload = None
    layer = None
    sessionname = None
    menuoptions = None

    self.lock.acquire()

    if jackclientname in self.jackclients:
      windowtitle = self.get_property_unlock(jackclientname,'windowtitle')
      guitoload = self.get_property_unlock(jackclientname,'guitoload')
      layer = self.get_property_unlock(jackclientname,'layer')
      sessionname = self.get_property_unlock(jackclientname,'sessionname')      

    self.lock.release()

    cmd = None
    if winid:
      if sessionname:
        cmd = ' '.join(['switchto', '--sessionname', '"' + sessionname+ '"', '--windowid', winid])
      elif guitoload:
        cmd = ' '.join(['switchto', '--guitoload', '"' + guitoload + '"', '--windowid', winid])
      else:
        cmd = ' '.join(['switchto', '--windowid', winid])
    else:
      args = []
      if windowtitle:
        args = ['--windowtitle' , '"'+windowtitle+'"']
      if guitoload:
        cmd = ' '.join(['switchto', '--guitoload', '"' + guitoload + '"'] + args)
      print ('Nothing to do')
    if cmd:
      print (cmd)
      os.system(cmd)
    if self.Debug:
      print ('>==== GroupPropertiesHelper:: loadOrSwitchToApp')


# ------------------------------------------------------------------------------------------------------------
# Main

if __name__ == '__main__':
  
  helper = GroupPropertiesHelper(Debug=True)
  
  input("Press Enter to quit...")
  helper.stop()
