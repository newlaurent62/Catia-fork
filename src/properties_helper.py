#!/usr/bin/env python3

import glob
import yaml
import os
import datetime as dt
import threading 
import subprocess
import shlex
import jack
import re

class GroupPropertiesHelper:
  
  def __init__(self, _dir='/tmp/catia', Debug=False):
    self.sched = None
    if not(os.path.isdir(_dir)):
      os.makedirs(_dir)
    self._dir = _dir
    self.jackclients = {}
    self.Debug = Debug
    self.layer_list = []
    self.lock = threading.Lock()
    sessionpath = None
    try:
      sessionpath = subprocess.check_output(['ray_control', 'get_session_path'], text=True)
    except Exception as e:
      if self.Debug:
        print (e)
      print ('Do you opened a Raysession document ?')
    
    if sessionpath:
      try:
        pathlist = os.path.split(sessionpath)      
        print (pathlist)
        _file = self._dir + os.sep + os.path.basename(pathlist[len(pathlist)-1].strip()) + ".yml"
        if os.path.isfile(_file):
          if self.Debug:
            print ('+ %s found.' % _file)
          self.updateProperties(_file)                
        else:
          if self.Debug:
            print ('- %s not found.' % _file)
      except Exception as e:
        print (e)
        
    self.eventStop = self.start(5)

  def start(self,interval):
    stopped = threading.Event()
    def loop():
      while not stopped.wait(interval): # the first call is in `interval` secs
        try:          
          self.read_dir()
        except Exception as ex:
          print(ex)
            
    t = threading.Thread(target=loop)
    t.daemon = True
    t.start()    
    return stopped.set
  
  def stop(self):
    self.eventStop()
  
  def read_dir(self):
    now = dt.datetime.now()
    ago = now-dt.timedelta(seconds=5)
    
    for root, dirs,files in os.walk(self._dir):  
        for fname in files:
            path = os.path.join(root, fname)
            try:
              st = os.stat(path)    
              mtime = dt.datetime.fromtimestamp(st.st_mtime)
              if mtime > ago and path.endswith('.yml'):
                  if self.Debug:
                    print('%s modified %s'%(path, mtime))
                  self.updateProperties(path)                
              if mtime > ago and path.endswith('.session_closed'):
                  if self.Debug:
                    print('%s modified %s'%(path, mtime))
                  self.updateSessionClosed(path)                
            except Exception as e:
              print (e)
              pass
            
  def updateProperties(self,_file):
    if self.Debug:
      print ('<==== GroupPropertiesHelper:: updateProperties')
    
    with open(_file) as f:        
      jackclients = {}
      data = yaml.load(f, Loader=yaml.FullLoader)
      sessionname = data['sessionname']
      for el in data['jackclients']:
        jackclients[el['name']] = {'name': el['name'], 'windowtitle':el['windowtitle'], 'layer': el['layer'], 'guitoload': el['guitoload'], 'sessionname': sessionname, 'clientid': el['clientid']}
        if el['layer'] not in self.layer_list:
          self.layer_list.append(el['layer'])
      
      self.lock.acquire()
      self.jackclients = jackclients      
      if self.Debug:
        print (self.jackclients)
      self.lock.release()

    if self.Debug:
      print ('>==== GroupPropertiesHelper:: updateProperties')

  
  def __getPidFromFile(self, jackclientname):
    
    if jackclientname not in self.jackclients:
      if self.Debug:
        print ('jackclientname not registered in properties: %s' % jackclientname)
      return 0
    
    sessionname = self.jackclients[jackclientname]['sessionname']
    clientid = self.jackclients[jackclientname]['clientid']
    
    
    if sessionname and clientid:
      try:
        with open(self._dir + os.sep + sessionname + '.' + clientid + '.pid') as f:
          pid = int(f.read().strip())
          return pid
      except Exception as e:
        print (e)
        pass
    return 0

  def updateSessionClosed(self, _file):
    if self.Debug:
      print ('<==== GroupPropertiesHelper:: updateSessionClosed')
    with open(_file) as f:
      values = os.path.basename(_file).split(".")
      sessionname = values[0]
      print ("sessionname:" + sessionname)
      self.lock.acquire()
      jackclienttoremove = []
      for jackclientname in self.jackclients:
        jackclient = self.jackclients[jackclientname]
        if jackclient['sessionname'] == sessionname:
          jackclienttoremove.append(jackclientname)
          if self.Debug:
            print ('%s removed.' % jackclientname)
      
      for jackclientname in jackclienttoremove:
        del self.jackclients[jackclientname]

      self.lock.release()
      try:
        os.remove(_file)
      except Exception as e:
        print (e)
        print('error during file remove %s' % pathfile)
        
      fileList = glob.glob(self._dir + os.sep + sessionname + '.*.pid', recursive=False)
      for pathfile in fileList:
        try:
          os.remove(pathfile)
        except Exception as e:
          print (e)
          print('error during file remove %s' % pathfile)
          
        if self.Debug:
          print ('  remove %s' % pathfile)
          
      if self.Debug:
        print (self.jackclients)
    if self.Debug:
      print ('>==== GroupPropertiesHelper:: updateSessionClosed')
    

      
  def getProperty(self, jackclientname, propertyname):
    self.lock.acquire()
    result = self.get_property_unlock(jackclientname, propertyname)
    self.lock.release()
    return result
  
  def get_property_unlock(self, jackclientname, propertyname):
    if propertyname == 'pid':
      # try to get pid from jacklib
      result = jack.client_pid(jackclientname)
      # otherwise we get pid from pid file
      if result == 0:
        pidfromfile = self.__getPidFromFile(jackclientname)
        result = int(pidfromfile)
      if self.Debug:
        print ('%s: %d' % (propertyname, result))
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
      
      if jackclientname in self.jackclients:
        windowtitle = self.get_property_unlock(jackclientname,'windowtitle')
        guitoload = self.get_property_unlock(jackclientname,'guitoload')
        layer = self.get_property_unlock(jackclientname,'layer')
        pid = self.get_property_unlock(jackclientname, 'pid')
        sessionname = self.get_property_unlock(jackclientname,'sessionname')      
        
        if self.Debug:
          print('--pid: %d\n--windowtitle:%s\n--guitoload:%s\n--layer:%s\n--sessionname:%s' % (pid,windowtitle,guitoload,layer,sessionname))
        
        if pid != 0 and windowtitle:
          menuoptions = self.getWinIdsAndtitlesFromPid(pid, regexp=windowtitle)
        elif pid != 0:
          menuoptions = self.getWinIdsAndtitlesFromPid(pid)
        elif pid == 0 and windowtitle:
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
  
  helper = GroupPropertiesHelper('/tmp/catia',Debug=True)
  
  input("Press Enter to quit...")
  helper.stop()
  
  print (str(helper.getProperty('jack_capture','windowtitle')))
  print (str(helper.getProperty('jack_capture','layer')))

  helper.loadOrSwitchToApp('system')
  
  helper.loadOrSwitchToApp('PulseAudio JACK Source')
