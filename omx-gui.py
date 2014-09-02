############################
# omx-gui w/ wxpython
# by gian pratama
# last update : August 16, 2014 
############################

# pyomxplayer from https://github.com/jbaiter/pyomxplayer
# modified by KenT

# ********************************
# PYOMXPLAYER
# ********************************

import pexpect
import re

from threading import Thread
from time import sleep

class OMXPlayer(object):
    
    _FILEPROP_REXP = re.compile(r".*audio streams (\d+) video streams (\d+) chapters (\d+) subtitles (\d+).*")
    _VIDEOPROP_REXP = re.compile(r".*Video codec ([\w-]+) width (\d+) height (\d+) profile (\d+) fps ([\d.]+).*")
    _AUDIOPROP_REXP = re.compile(r"Audio codec (\w+) channels (\d+) samplerate (\d+) bitspersample (\d+).*")
    _STATUS_REXP = re.compile(r"V :\s*([\d.]+).*")
    _DONE_REXP = re.compile(r"have a nice day.*")

    _LAUNCH_CMD = '/usr/bin/omxplayer -s %s %s'
    _PAUSE_CMD = 'p'
    _TOGGLE_SUB_CMD = 's'
    _QUIT_CMD = 'q'

    paused = False
    # KRT turn subtitles off as a command option is used
    subtitles_visible = False

    #****** KenT added argument to control dictionary generation
    def __init__(self, mediafile, args=None, start_playback=False, do_dict=False):
        if not args:
            args = ""
        #******* KenT signals to tell the gui playing has started and ended
        self.start_play_signal = False
        self.end_play_signal=False
        cmd = self._LAUNCH_CMD % (mediafile, args)
        self._process = pexpect.spawn(cmd)
        # fout= file('logfile.txt','w')
        # self._process.logfile_send = sys.stdout
        
        # ******* KenT dictionary generation moved to a function so it can be omitted.
        if do_dict:
            self.make_dict()
            
        self._position_thread = Thread(target=self._get_position)
        self._position_thread.start()
        if not start_playback:
            self.toggle_pause() 
        # don't use toggle as it seems to have a delay
        # self.toggle_subtitles()


    def _get_position(self):
    
        # ***** KenT added signals to allow polling for end by a gui event loop and also to check if a track is playing before
        # sending a command to omxplayer
        self.start_play_signal = True
        print "start_play_signal"

        # **** KenT Added self.position=0. Required if dictionary creation is commented out. Possibly best to leave it in even if not
        #         commented out in case gui reads position before it is first written.
        self.position=-100.0
        
        while True:
            index = self._process.expect([self._STATUS_REXP,
                                            pexpect.TIMEOUT,
                                            pexpect.EOF,
                                            self._DONE_REXP])
            if index == 1: continue
            elif index in (2, 3):
                # ******* KenT added
                self.end_play_signal=True
                break
            else:
                self.position = float(self._process.match.group(1))                
            sleep(0.05)

    def make_dict(self):
        self.video = dict()
        self.audio = dict()

        #******* KenT add exception handling to make code resilient.
        
        # Get file properties
        try:
            file_props = self._FILEPROP_REXP.match(self._process.readline()).groups()
        except AttributeError:
            return False        
        (self.audio['streams'], self.video['streams'],
        self.chapters, self.subtitles) = [int(x) for x in file_props]
        
        # Get video properties        
        try:
            aspect_props = self._proccess.readline()
            video_props = self._VIDEOPROP_REXP.match(self._process.readline()).groups()
        except AttributeError:
            return False
        self.video['decoder'] = video_props[0]
        self.video['dimensions'] = tuple(int(x) for x in video_props[1:3])
        self.video['profile'] = int(video_props[3])
        self.video['fps'] = float(video_props[4])
                        
        # Get audio properties
        try:
            audio_props = self._AUDIOPROP_REXP.match(self._process.readline()).groups()
        except AttributeError:
            return False       
        self.audio['decoder'] = audio_props[0]
        (self.audio['channels'], self.audio['rate'],
         self.audio['bps']) = [int(x) for x in audio_props[1:]]

        if self.audio['streams'] > 0:
            self.current_audio_stream = 1
            self.current_volume = 0.0

# ******* KenT added basic command sending function
    def send_command(self,command):
        self._process.send(command)
        print "def send_command"
        return True

# ******* KenT added test of whether _process is running (not certain this is necessary)
    def is_running(self):
        return self._process.isalive()
        print "def is_running"

    def toggle_pause(self):
        if self._process.send(self._PAUSE_CMD):
            self.paused = not self.paused
            print "def toggle_pause"

    def toggle_subtitles(self):
        if self._process.send(self._TOGGLE_SUB_CMD):
            self.subtitles_visible = not self.subtitles_visible
            print "def toggle_subs"
            
    def stop(self):
        self._process.send(self._QUIT_CMD)
        self._process.terminate(force=True)
        print "def stop"

    def set_speed(self):
        raise NotImplementedError

    def set_audiochannel(self, channel_idx):
        raise NotImplementedError

    def set_subtitles(self, sub_idx):
        raise NotImplementedError

    def set_chapter(self, chapter_idx):
        raise NotImplementedError

    def set_volume(self, volume):
        raise NotImplementedError
        print "def set_volume" 

    def seek(self, minutes):
        raise NotImplementedError


#from pyomxplayer import OMXPlayer
from threading import Thread
from time import sleep

from pprint import pformat
from pprint import pprint
from Tkinter import *
import Tkinter as tk
import FileDialog
import tkMessageBox
import tkSimpleDialog
import csv
import ConfigParser

import wx
import wx.media
import wx.lib.buttons as buttons
import os
import subprocess

##################
# OMX-GUI CLASS
##################

class melody_wrapper(wx.Frame):

    def init_play_state_machine(self):


        self._OMX_CLOSED = "omx_closed"
        self._OMX_STARTING = "omx_starting"
        self._OMX_PLAYING = "omx_playing"
        self._OMX_ENDING = "omx_ending"

        # what to do next signals
        self.break_required_signal=False         # signal to break out of Repeat or Playlist loop
        self.play_previous_track_signal = False
        self.play_next_track_signal = False

         # playing a track signals
        self.stop_required_signal=False
        self.play_state=self._OMX_CLOSED
        self.quit_sent_signal = False          # signal  that q has been sent
        self.paused=False


# kick off the state machine by playing a track
    def play(self):
        if  self.play_state==self._OMX_CLOSED:
            if self.playlist.track_is_selected():
                #initialise all the state machine variables
                self.iteration = 0                             # for debugging
                self.paused = False
                self.stop_required_signal=False     # signal that user has pressed stop
                self.quit_sent_signal = False          # signal  that q has been sent
                self.play_state=self._OMX_STARTING
                
                #play the selelected track
                self.start_omx(self.playlist.selected_track_location)
                self.root.after(500, self.play_state_machine)
                
                print "def play"
 
    def play_state_machine(self):
        # self.monitor ("******Iteration: " + str(self.iteration))
        self.iteration +=1
        if self.play_state == self._OMX_CLOSED:
            self.what_next()
            return 
                
        elif self.play_state == self._OMX_STARTING:
            if self.omx.start_play_signal==True:
                self.omx.start_play_signal=False
                self.play_state=self._OMX_PLAYING
            self.root.after(500, self.play_state_machine)

        elif self.play_state == self._OMX_PLAYING:
            if self.stop_required_signal==True:
                self.stop_omx()
                self.stop_required_signal=False
            else:
                if self.quit_sent_signal == True or self.omx.end_play_signal== True:
                    if self.quit_sent_signal:
                        self.quit_sent_signal = False
                    self.play_state =self. _OMX_ENDING
                self.do_playing()
            self.root.after(500, self.play_state_machine)

        elif self.play_state == self._OMX_ENDING:
            if self.omx.is_running() ==False:
                self.play_state = self._OMX_CLOSED
            self.do_ending()
            self.root.after(500, self.play_state_machine)


    # do things in each state
 
    def do_playing(self):
            if self.paused == False:
                self.display_time.set(self.time_string(self.omx.position))
                print "def do_playing : display_time.set(omx.pos)"
            else:
                self.display_time.set("Paused")
                print "def do_playing : display_time.set(paused)"

    def do_starting(self):
        self.display_time.set("Starting")
        print "def do_starting : display_time.set(starting)"
        return

    def do_ending(self):
        self.display_time.set("End")
        print "def do_ending : display_time.set(end)"
   
    def play_track(self,event):
        if self.play_state ==  self._OMX_PLAYING: 
            self.omx.stop()
            self.send_command('q')
            self.play_state=self._OMX_CLOSED
            self.play()
        else: 
           if self.play_state == self._OMX_CLOSED:
               self.play()
               print "def play_track : self.play()"

    def skip_to_next_track(self,event):
        self.monitor(">skip  to next received") 
        self.monitor(">stop received for next track") 
        self.stop_required_signal=True
        self.play_next_track_signal=True
        print "def skip_to_next_track"
        

    def skip_to_previous_track(self,event):
        self.monitor(">skip  to previous received")
        self.monitor(">stop received for previous track") 
        self.stop_required_signal=True
        self.play_previous_track_signal=True
        print "def skip_to_prev_track"


    def stop_track(self,event):
        self.send_command('q')
        self.stop_required_signal=True
        self.break_required_signal=True
        self.play_state=self._OMX_CLOSED
        print "def stop_track"


    def toggle_pause(self,event):
        """pause clicked Pauses or unpauses the track"""
        self.send_command('p')
        if self.paused == False:
            self.paused=True
            print "def toogle_pause"
        else:
            self.paused=False

    def del_track(self,event):
        select = self.playlist_box.GetSelection()
        if select != 1 :
            self.playlist_box.Delete(select)

    def volplus(self,event):
        self.send_command('+')
        print "def vol_plus"
        
    def volminus(self,event):
        self.send_command('-')
        print "def vol_minus"

    def time_string(self,secs):
        minu = int(secs/60)
        sec = secs-(minu*60)
        return str(minu)+":"+str(int(sec))

    def what_next(self):
        if self.play_next_track_signal ==True:
            self.select_next_track()
            self.play_next_track_signal=False
            self.play()
            return
        elif self.play_previous_track_signal ==True:
            self.select_previous_track()
            self.play_previous_track_signal=False
            self.play()
            return
        elif self.break_required_signal==True:
            self.break_required_signal=False
            return
        elif self.options.mode=='single':
            return
        elif self.options.mode=='repeat':
            self.play()
            return
        elif self.options.mode=='playlist':
            self.select_next_track()
            self.play()
            return     

# ***************************************
# WRAPPER FOR JBAITER'S PYOMXPLAYER
# ***************************************

    def start_omx(self,track):
        """ Loads and plays the track"""
        track= "'"+ track.replace("'","'\\''") + "'"
        opts= self.options.omx_audio_option + " "
        self.omx = OMXPlayer(track, opts, start_playback=True) #do_dict=self.options.generate_track_info)
        print "def start_omx"

    def stop_omx(self):
        if self.play_state ==  self._OMX_PLAYING:
            self.omx.stop()
            print "def stop_omx"
        else:
            self.monitor ("            !>stop not sent to OMX because track not playing")
            
            
    def send_command(self,command):
        if (command in '+-pz12jkionmsq') :#and self.play_state ==  self._OMX_PLAYING:
            self.omx.send_command(command)
            print "def send_command "+command
            return True
        else:
            return False

    def send_special(self,command):
        if self.play_state ==  self._OMX_PLAYING:
            self.omx.send_command(command)
            return True
        else:
            return False
        
################
# INIT
################

    def __init__(self,parent,id):
        
        wx.Frame.__init__(self,parent,id,'OMX-GUI', size=(408,300), style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)
        panel=wx.Panel(self)
        self.root = tk.Tk()

        # inisialise playback slider, timer and volume 
        self.frame = parent
        self.currentVolume = 0.00

        # initialise options class and do initial reading/creation of options
        self.options=Options()

        #initialise the play state machine
        self.init_play_state_machine()

        #create the internal playlist
        self.playlist = PlayList()

        # bind some display fields #check it
        self.filename = tk.StringVar()
        self.display_selected_track_title = tk.StringVar()
        self.display_time = tk.StringVar()

        #Keys
        self.root.bind("<Left>", self.key_left)
        self.root.bind("<Right>", self.key_right)
        self.root.bind("<Shift-Right>", self.key_shiftright)  #forward 600
        self.root.bind("<Shift-Left>", self.key_shiftleft)  #back 600
        self.root.bind("<Control-Right>", self.key_ctrlright)  #previous track      
        self.root.bind("<Control-Left>", self.key_ctrlleft)  #previous track
        self.root.bind("<Delete>", self.key_delete)
        self.root.bind("<Key>", self.key_pressed)
        
# MENU-BAR #
        status=self.CreateStatusBar
        menubar=wx.MenuBar()

        file_menu=wx.Menu()
        control_menu=wx.Menu()
        help_menu=wx.Menu()

#--file--#
        file_menu.Append(1,"Add File","Add some file to play")
        self.Bind(wx.EVT_MENU, self.add_track, id=1)
        
        file_menu.Append(2,"Open Playlist","Open playlist from file")
        self.Bind(wx.EVT_MENU, self.open_list, id=2)
        
        file_menu.Append(3,"Save Playlist","Save playlist to file")
        self.Bind(wx.EVT_MENU, self.save_list, id=3)
        
        file_menu.Append(4,"Clear Playlist","Clear playlist field")
        self.Bind(wx.EVT_MENU, self.clear_list, id=4)
        
#--control--#
        control_menu.Append(5,"Edit", "Edit Output and Playlist Mode")
        self.Bind(wx.EVT_MENU, self.edit_options, id=5)
        
#--help--#
        help_menu.Append(6,"Shortcut Info", "Shortcut Information")
        self.Bind(wx.EVT_MENU, self.Shortcut, id=6)
        
        help_menu.Append(7,"About", "About OMX-GUI")
        self.Bind(wx.EVT_MENU, self.About, id=7)

        menubar.Append(file_menu,"File")        
        menubar.Append(control_menu,"Control")
        menubar.Append(help_menu,"Help")

        self.SetMenuBar(menubar)

# listbox-playlist #
        self.melodylist=[]
        self.playlist_box = wx.ListBox(panel, -1, (10,10), (390,175),self.melodylist, wx.LB_SINGLE)
        self.playlist_box.Bind(wx.EVT_LISTBOX, self.select_track)

# button-bar #

        prev_button=wx.Image("player_prev.png").ConvertToBitmap()
        self.button=wx.BitmapButton(panel, -1, prev_button, pos=(10,220))
        self.Bind(wx.EVT_BUTTON, self.select_previous_track, self.button) 

        play_button=wx.Image("player_play.png").ConvertToBitmap()
        self.button=wx.BitmapButton(panel, -1, play_button, pos=(60,220))
        self.Bind(wx.EVT_BUTTON, self.play_track, self.button)

        pause_button=wx.Image("player_pause.png").ConvertToBitmap()
        self.button=wx.BitmapButton(panel, -1, pause_button, pos=(110,220))
        self.Bind(wx.EVT_BUTTON, self.toggle_pause, self.button)

        stop_button=wx.Image("player_stop.png").ConvertToBitmap()
        self.button=wx.BitmapButton(panel, -1, stop_button, pos=(160,220))
        self.Bind(wx.EVT_BUTTON, self.stop_track, self.button)
   
        next_button=wx.Image("player_next.png").ConvertToBitmap()
        self.button=wx.BitmapButton(panel, -1, next_button, pos=(210,220))
        self.Bind(wx.EVT_BUTTON, self.select_next_track, self.button)

        
# slider - time & volume #
        mute_button=wx.Image("sound.png").ConvertToBitmap()
        self.button=wx.BitmapButton(panel, -1, mute_button, pos=(270,230))
        self.Bind(wx.EVT_BUTTON, self.mute, self.button)
        
        self.vol_slider=wx.Slider(panel, -1, 50, 1, 100, pos=(300,219), size=(100,-1), style=wx.SL_AUTOTICKS | wx.SL_HORIZONTAL | wx.SL_LABELS)
        self.vol_slider.Bind(wx.EVT_SLIDER, self.slider_update)
        
# ***************************************
# MISCELLANEOUS
# ***************************************

    def mute(self,event):
        self.currentVolume==0

    def slider_update(self,event):
        self.vol_pos = self.vol_slider.GetValue()

        if self.vol_pos < self.currentVolume :
            self.send_command('-')
            self.vol_slider.SetValue(self.vol_pos)
            self.currentVolume = self.vol_pos    
            print "vol - , set to "+str(self.currentVolume) 
            #return
        
        elif self.vol_pos > self.currentVolume :
            self.send_command('+')
            self.vol_slider.SetValue(self.vol_pos)
            self.currentVolume = self.vol_pos
            print "vol + , set to "+str(self.currentVolume)   
            #return

    def edit_options(self,event):
        """edit the options then read them from file"""
        OptionsDialog(self, self.options.options_file,'Edit Options').Show()
        self.options.read(self.options.options_file)
        print "def edit_options"
  
    def monitor(self,text):
        if self.options.debug: print text
        
# Key Press callbacks

    def key_right(self,event):
        self.send_special('\x1b\x5b\x43')
        print "def key_right"

    def key_left(self,event):
        self.send_special('\x1b\x5b\x44')
        print "def key_left"
        
    def key_shiftright(self,event):
        self.send_special('\x1b\x5b\x42')
        print "def key_shiftright"

    def key_shiftleft(self,event):
        self.send_special('\x1b\x5b\x41')
        print "def key_shiftleft"

    def key_ctrlright(self,event):
        self.skip_to_next_track()
        print "def key_ctrlright"

    def key_ctrlleft(self,event):
        self.skip_to_previous_track()
        print "def key_ctrlleft"

    def key_delete(self,event):
        self.del_track()
        print "delete track"

    def key_pressed(self,event):
        char = event.char
        if char=='':
            return
        elif char=='.':
            self.play_track()
            print ". pressed"
        elif char=='p':
            self.toggle_pause()
            print "p pressed"
            return
        elif char==' ':
            self.toggle_pause()
            print "space pressed"
            return
        elif char=='q':
            self.stop_track()
            print "q pressed"
            return
        else:
            self.send_command(char)
            return

# ***************************************
# DISPLAY TRACKS
# ***************************************

    def display_selected_track(self,index):
        if self.playlist.track_is_selected:
            self.playlist_box.Select(index)   
            self.display_selected_track_title.set(self.playlist.selected_track()[PlayList.TITLE])
            print "def display_selected_track "+str(PlayList.TITLE)
        else:
            self.display_selected_track_title.set("")

    def blank_selected_track(self):
            self.display_selected_track_title.set("")
            print "def blank_selected_track"

    def refresh_playlist_display(self):
        self.playlist_box.delete(0,self.playlist_box.size())
        for index in range(self.playlist.length()):
            self.playlist.select(index)
            print "def refresh_playlist_display"
            
###########
# TRACK & PLAYLIST CALLBACK
###########

    def add_track(self, event):
        """
        Opens a window to open a file,
        then stores the  track in the playlist
        """
        # get the file
        userPath = '/home/pi/'
        wildcard = "MP3 File (*.mp3)|*.mp3|"
                   
        dialog = wx.FileDialog(None, "Choose file to Play :", style=1, defaultDir=userPath, wildcard=wildcard, pos=(10,10))

        if dialog.ShowModal()==wx.ID_OK:
            self.path = dialog.GetPath()
            print "def add_track, path : "+self.path
            self.filename = dialog.GetFilename()  #get the filename of the file
            print "def add_track, filename : "+self.filename
            self.dirname = dialog.GetDirectory()  #get the directory of where file is located

        # split it to use leaf as the initial title      
            self.file_pieces = self.filename.split("/")
            
        # append it to the playlist
            self.playlist_box.Append(self.filename)
            self.playlist.append([self.path, self.file_pieces[-1],'',''])
            print "def add_track : append it to the playlist " +str(self.file_pieces)
            print "def add_track : add title to playlist display as " +str(self.filename)
            
        # and set it as the selected track
            self.playlist.select(self.playlist.length()-1)
            self.display_selected_track(self.playlist.selected_track_index())
            print "def add_track : set it as the selected track"
            print "index play : "+str(self.playlist.selected_track_index())

        return        

        dialog.Destroy()
            
    def select_track(self, event):
        """
        user clicks on a track in the display list so try and select it
        """
        # needs forgiving int for possible tkinter upgrade
        if self.playlist.length()>0:
            index=int(event.GetSelection())
            self.playlist.select(index)
            self.display_selected_track(index)

    def select_next_track(self,event): #next_btn
        if self.playlist.length()>0:
            if self.playlist.selected_track_index()== self.playlist.length()-1:
                index=0
            else:
                index= self.playlist.selected_track_index()+1
            self.stop_track(event)
            self.playlist.select(index)
            self.display_selected_track(index)
            self.play_track(event)
            print "def select_next_track"

                
    def select_previous_track(self,event): #prev_btn
        if self.playlist.length()>0:
            if self.playlist.selected_track_index()== 0:
                index=self.playlist.length()-1
            else:
               index = self.playlist.selected_track_index()- 1

            self.stop_track(event)
            self.playlist.select(index)               
            self.display_selected_track(index)
            self.play_track(event)
            print "def select_prev_track"
    
    def Shortcut(self,event):
        ShortcutFrame().Show()

    def About(self,event):
        AboutFrame().Show()

##############
# CLASS - PLAYLISTS
##############

    def open_list(self,event):
        """
        opens a saved playlist
        playlists are stored as textfiles each record being "path","title"
        """

        userPath = '/home/pi/'
        wildcard = "Playlist File (*.csv)|*.csv|" 
                   
        dialog = wx.FileDialog(self, "Open Playlist File :", style=1, defaultDir=userPath, wildcard=wildcard, pos=(10,10))

        if dialog.ShowModal()==wx.ID_OK:
            path = dialog.GetPath() 
            filename = dialog.GetFilename()  #get the filename of the file
            dirname = dialog.GetDirectory()  #get the directory of where file is located
        
            if filename=="":
                return
            ifile  = open(filename, 'rb')
            pl=csv.reader(ifile)
            self.playlist.clear()

            for pl_row in pl:
                if len(pl_row) != 0:
                    self.playlist.append([pl_row[0],pl_row[1],'',''])
                    self.playlist_box.Append(pl_row[1])

            ifile.close()
            self.playlist.select(0)
            self.display_selected_track(0)
            return
        return

    def save_list(self,event):
        """ save a playlist """
        self.dirname=''
        dlg = wx.FileDialog(self, "Save Playlist", self.dirname, "", "*.csv*", \
                wx.SAVE | wx.OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            
            filename=dlg.GetFilename()
            self.dirname=dlg.GetDirectory()
            if filename=="":
                return
            ofile  = open(filename, "wb")
            for idx in range(self.playlist.length()):
                    self.playlist.select(idx)
                    ofile.write ('"' + self.playlist.selected_track()[PlayList.LOCATION] + '","' + self.playlist.selected_track()[PlayList.TITLE]+'"\n')
            ofile.close()
            return

    def clear_list(self,event):
            self.playlist_box.Clear()
            self.playlist.clear()
            self.blank_selected_track()
            print "clear list"
                       
##############
# CLASS - ABOUT
##############
      
class AboutFrame(wx.Frame):
    title ="About OMX-GUI"

    def __init__(self):
        wx.Frame.__init__(self, wx.GetApp().TopWindow, title=self.title, size=(300,100))
        panel=wx.Panel(self)

        about_text=wx.StaticText(panel, -1, "OMX-GUI w/ wxpython", pos=(90,25))
        about_text1=wx.StaticText(panel, -1, "by Gian Pratama (gianpratama880@gmail.com)", pos=(35,45))
        about_text2=wx.StaticText(panel, -1, "Thanks to : jbaiter & KenT", pos=(80,65))

class ShortcutFrame(wx.Frame):
    title ="Shortcut Info"

    def __init__(self):
        wx.Frame.__init__(self, wx.GetApp().TopWindow, title=self.title, size=(300,300))
        panel=wx.Panel(self)
        
        about_text=wx.StaticText(panel, -1, " To control playing, type a character\n p : pause/play\n spacebar - pause/play\n q - quit\n"
        + "+ : increase volume\n - : decrease volume\n z : tv show info\n 1 : reduce speed\n"
        + "2 : increase speed\n j : previous audio index\n k : next audio index\n i : back a chapter\n"
        + "o : forward a chapter\n n : previous subtitle index\n m : next subtitle index\n"
        + "s : toggle subtitles\n >cursor : seek forward 30\n <cursor : seek back 30\n"
        + "SHIFT >cursor : seek forward 600\n SHIFT <cursor : seek back 600\n"
        + "CTRL >cursor : next track\n CTRL <cursor : previous track" ,pos=(10,10))


# ***************************************
# OPTIONS CLASS
# ***************************************

class Options:


# store associated with the object is the tins file. Variables used by the player
# is just a cached interface.
# options dialog class is a second class that reads and saves the otions from the options file

    def __init__(self):

        # define options for interface with player
        self.omx_audio_option = "" # omx audio option
        self.mode = ""

    # create an options file if necessary
        self.options_file = 'config.cfg'
        if os.path.exists(self.options_file):
            self.read(self.options_file)
        else:
            self.create(self.options_file)
            self.read(self.options_file)
    
    def read(self,filename):
        """reads options from options file to interface"""
        config=ConfigParser.ConfigParser()
        config.read(filename)
        
        if  config.get('config','audio',0)=='auto':
             self.omx_audio_option=""
        else:
            self.omx_audio_option = "-o "+config.get('config','audio',0)
            
        self.mode = config.get('config','mode',0)

        print "audio opt = "+str(self.omx_audio_option)
        print "mode opt = "+str(self.mode)
        
         
    def create(self,filename):
        config=ConfigParser.ConfigParser()
        config.add_section('config')
        config.set('config','audio','local')
        config.set('config','mode','single')
        with open(filename, 'wb') as configfile:
            config.write(configfile)
            print "def create options success"


# *************************************
# OPTIONS DIALOG CLASS 
# ************************************

class OptionsDialog(wx.Frame): 
    title ="Edit Options"

    def __init__(self, parent, options_file, title=None):
        self.dialog = wx.Frame.__init__(self, wx.GetApp().TopWindow, title=self.title, size=(230,300), style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)
        panel=wx.Panel(self)
        print "Options_dialog frame"

        # store subclass attributes
        self.options_file=options_file

        config=ConfigParser.ConfigParser()
        config.read(self.options_file)

        self.audio_var=StringVar()        
        audio_title=wx.StaticText(panel, -1, label="Audio Output :", pos=(20,20))
        self.local = wx.RadioButton(panel, label="Local", style=wx.RB_GROUP)
        self.hdmi = wx.RadioButton(panel, label="HDMI")
        self.auto = wx.RadioButton(panel, label="Auto")

        self.mode_var=StringVar()
        mode_title=wx.StaticText(panel, -1, label="Mode :", pos=(20,180))
        self.single = wx.RadioButton(panel, label="Single", style=wx.RB_GROUP)     
        self.repeat = wx.RadioButton(panel, label="Repeat")
        self.playlist = wx.RadioButton(panel, label="Playlist")

        ok_btn = wx.Button(panel, label="OK", pos=(25,250))
        ok_btn.Bind(wx.EVT_BUTTON, self.apply)
        
        cancel_btn = wx.Button(panel, label="Cancel", pos=(115,250))
        cancel_btn.Bind(wx.EVT_BUTTON, self.cancel)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(audio_title, 0, wx.ALL, 5)
        sizer.Add(self.local, 0, wx.ALL, 5)
        sizer.Add(self.hdmi, 0, wx.ALL, 5)
        sizer.Add(self.auto, 0, wx.ALL, 5)
        sizer.Add(mode_title, 0, wx.ALL, 5)
        sizer.Add(self.single, 0, wx.ALL,5)
        sizer.Add(self.repeat, 0, wx.ALL,5)
        sizer.Add(self.playlist, 0, wx.ALL,5)
        panel.SetSizer(sizer)

    def cancel(self,event):
        self.Close(True)
        print "Cancel"
                
    def apply(self,event):    
        self.save_options()
        print "def apply : options saved"
        return True

    def save_options(self):
        """ save the output of the options edit dialog to file"""
        config=ConfigParser.ConfigParser()
        config.add_section('config')

        if self.hdmi.GetValue()==True:
            config.set('config','audio','hdmi')
            with open(self.options_file, 'wb') as optionsfile:
                config.write(optionsfile)
            print "hdmi"
        elif self.auto.GetValue()==True:
            config.set('config','audio','auto')
            with open(self.options_file, 'wb') as optionsfile:
                config.write(optionsfile)
            print "auto" 
        else :
            config.set('config','audio','local')
            with open(self.options_file, 'wb') as optionsfile:
                config.write(optionsfile)
            print "local"

        if self.repeat.GetValue()==True:
            config.set('config','mode','repeat')
            with open(self.options_file, 'wb') as optionsfile:
                config.write(optionsfile)
            print "repeat"
        elif self.playlist.GetValue()==True:
            config.set('config','mode','playlist')
            with open(self.options_file, 'wb') as optionsfile:
                config.write(optionsfile)
            print "playlist"
        else :
            config.set('config','mode','single')
            with open(self.options_file, 'wb') as optionsfile:
                config.write(optionsfile)
            print "single"
            

# *************************************
# EDIT TRACK DIALOG CLASS
# ************************************

class EditTrackDialog(tkSimpleDialog.Dialog):

    def __init__(self, parent, title=None, *args):
        #save the extra args to instance variables
        self.label_location=args[0]
        self.default_location=args[1]       
        self.label_title=args[2]
        self.default_title=args[3]
        tkSimpleDialog.Dialog.__init__(self, parent, title)


    def body(self, master):
        Label(master, text=self.label_location).grid(row=0)
        Label(master, text=self.label_title).grid(row=1)

        self.field1 = Entry(master)
        self.field2 = Entry(master)

        self.field1.grid(row=0, column=1)
        self.field2.grid(row=1, column=1)

        self.field1.insert(0,self.default_location)
        self.field2.insert(0,self.default_title)

        return self.field2 # initial focus on title


    def apply(self):
        first = self.field1.get()
        second = self.field2.get()
        self.result = first, second,'',''
        return self.result

#############
# CLASS - PLAYLIST
##############
class PlayList():
    
    #field definition constants
    LOCATION=0
    TITLE=1
    DURATION=2
    ARTIST=3

    # template for a new track
    _new_track=['','','','']
    

    def __init__(self):
        self._num_tracks=0
        self._tracks = []      # list of track titles
        self._selected_track = PlayList._new_track
        self._selected_track_index =  0 # index of currently selected track
        self._tracks=[]     #playlist, stored as a list of lists

    def length(self): # panjang playlist
        return self._num_tracks

    def track_is_selected(self):
            if self._selected_track_index>=0:
                return True
            else:
                return False
            
    def selected_track_index(self):
        return self._selected_track_index

    def selected_track(self):
        return self._selected_track

    def append(self, track):
        """appends a track to the end of the playlist store"""
        self._tracks.append(track)
        self._num_tracks+=1

    def remove(self,index):
        self._tracks.pop(index)
        self._num_tracks-=1
        self._selected_track_index=-1

    def clear(self):
            self._tracks = []
            self._num_tracks=0
            self._track_locations = []
            self._selected_track_index=-1
            self.selected_track_title=""
            self.selected_track_location=""

    def replace(self,index,replacement):
        self._tracks[index]= replacement           

    def select(self,index):
        """does housekeeping necessary when a track is selected"""
        if self._num_tracks>0 and index<= self._num_tracks:
            self._selected_track_index=index
            print "select track index = "+str(self._selected_track_index)
            self._selected_track = self._tracks[index]
            print "select track = "+str(self._selected_track) 
            self.selected_track_location = self._selected_track[PlayList.LOCATION]
            print "def PlayList select loc "+str(PlayList.LOCATION)
            self.selected_track_title = self._selected_track[PlayList.TITLE]
            print "def PlayList select title "+str(self.selected_track_title)           
        else :
            print "select failed"
        
############            
# MAIN
############ 

if __name__=="__main__":
            app=wx.PySimpleApp()
            frame=melody_wrapper(parent=None,id=-1)
            frame.Show()             
            app.MainLoop()
