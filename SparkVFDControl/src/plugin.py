# for localized messages
from . import _

from Screens.Screen import Screen
from Components.Console import Console
from Components.Button import Button
from Components.ActionMap import ActionMap
from Components.config import config, configfile, ConfigSubsection, ConfigEnableDisable, getConfigListEntry, ConfigInteger, ConfigSelection, ConfigYesNo
from Components.ConfigList import ConfigListScreen, ConfigList
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from enigma import iPlayableService, eServiceCenter, eTimer
from os import system
from Plugins.Plugin import PluginDescriptor
from Components.ServiceEventTracker import ServiceEventTracker
from Components.ServiceList import ServiceList
from Screens.InfoBar import InfoBar
from time import localtime, time
import Screens.Standby
from enigma import evfd

config.plugins.VFD_spark = ConfigSubsection()
config.plugins.VFD_spark.ledMode = ConfigSelection(default = "True", choices = [("False",_("Led in Standby off")),("True",_("Led in Standby on"))])
config.plugins.VFD_spark.textMode = ConfigSelection(default = "ChNumber", choices = [("ChNumber",_("Channel number")),("ChName",_("Channel name"))])

class Channelnumber:

	def __init__(self, session):
		self.session = session
		self.updatetime = 1000
		self.zaPrik = eTimer()
		self.zaPrik.timeout.get().append(self.vrime)
		self.zaPrik.start(60*1000, 1)
		self.onClose = [ ]

		self.__event_tracker = ServiceEventTracker(screen=self,eventmap=
			{
				iPlayableService.evUpdatedEventInfo: self.__eventInfoChanged
			})

	def __eventInfoChanged(self):
		if Screens.Standby.inStandby:
			return
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		if info is None:
			vfdtext = "---"
		else:
			if config.plugins.VFD_spark.textMode.value == 'ChNumber':
				vfdtext = self.getchannelnr()
			elif config.plugins.VFD_spark.textMode.value == 'ChName':
				vfdtext = info.getName().replace('\xc2\x86', '').replace('\xc2\x87', '')
			else:
				vfdtext = "---"
		info = None
		service = None
		evfd.getInstance().vfd_write_string(vfdtext)

	def getchannelnr(self):
		if InfoBar.instance is None:
			chnr = "---"
			return chnr
		MYCHANSEL = InfoBar.instance.servicelist
		markersOffset = 0
		myRoot = MYCHANSEL.getRoot()
		mySrv = MYCHANSEL.servicelist.getCurrent()
		chx = MYCHANSEL.servicelist.l.lookupService(mySrv)
		if not MYCHANSEL.inBouquet():
			pass
		else:
			serviceHandler = eServiceCenter.getInstance()
			mySSS = serviceHandler.list(myRoot)
			SRVList = mySSS and mySSS.getContent("SN", True)
			for i in range(len(SRVList)):
				if chx == i:
					break
				testlinet = SRVList[i]
				testline = testlinet[0].split(":")
				if testline[1] == "64":
					markersOffset = markersOffset + 1
		chx = (chx - markersOffset) + 1
		rx = MYCHANSEL.getBouquetNumOffset(myRoot)
		chnr = str(chx + rx)
		########## Center Channel number #################
		t = len(chnr)
		if t == 1:
			CentChnr = "000" + chnr + '\n'
		elif t == 2:
			CentChnr = "00" + chnr + '\n'
		elif t == 3:
			CentChnr = "0" + chnr + '\n'
		else:
			CentChnr = chnr + '\n'
		#################################################
		return CentChnr

	def vrime(self):
		clock=int(time())
		evfd.getInstance().vfd_set_clock(clock)	

ChannelnumberInstance = None

def leaveStandby():
	print "[VFD-SPARK] Leave Standby"
	evfd.getInstance().vfd_write_string("....")
	if config.plugins.VFD_spark.ledMode.value == 'True':
		evfd.getInstance().vfd_set_light(0)

def standbyCounterChanged(configElement):
	print "[VFD-SPARK] In Standby"
	from Screens.Standby import inStandby
	inStandby.onClose.append(leaveStandby)
	evfd.getInstance().vfd_clear_string()
	if config.plugins.VFD_spark.ledMode.value == 'True':
		evfd.getInstance().vfd_set_light(1)

def initVFD():
	print "[VFD-SPARK] initVFD"
	evfd.getInstance().vfd_write_string("....")
	clock=int(time())
	evfd.getInstance().vfd_set_clock(clock)
	evfd.getInstance().vfd_set_light(0)

class VFD_SparkSetup(ConfigListScreen, Screen):
	def __init__(self, session, args = None):

		self.skin = """
			<screen position="100,100" size="500,210" title="VFD Spark Setup" >
				<widget name="config" position="20,15" size="460,150" scrollbarMode="showOnDemand" />
				<ePixmap position="40,165" size="140,40" pixmap="skin_default/buttons/green.png" alphatest="on" />
				<ePixmap position="180,165" size="140,40" pixmap="skin_default/buttons/red.png" alphatest="on" />
				<widget name="key_green" position="40,165" size="140,40" font="Regular;20" backgroundColor="#1f771f" zPosition="2" transparent="1" shadowColor="black" shadowOffset="-1,-1" />
				<widget name="key_red" position="180,165" size="140,40" font="Regular;20" backgroundColor="#9f1313" zPosition="2" transparent="1" shadowColor="black" shadowOffset="-1,-1" />
			</screen>"""

		Screen.__init__(self, session)
		self.onClose.append(self.abort)

		self.onChangedEntry = [ ]
		self.list = []
		ConfigListScreen.__init__(self, self.list, session = self.session, on_change = self.changedEntry)

		self.createSetup()

		self.Console = Console()
		self["key_red"] = Button(_("Cancel"))
		self["key_green"] = Button(_("Save"))
		self["key_yellow"] = Button(_("Update Date/Time"))

		self["setupActions"] = ActionMap(["SetupActions","ColorActions"],
		{
			"save": self.save,
			"cancel": self.cancel,
			"ok": self.save,
			"yellow": self.Update,
		}, -2)

	def createSetup(self):
		self.editListEntry = None
		self.list = []
		self.list.append(getConfigListEntry(_("VFD text"), config.plugins.VFD_spark.textMode))
		self.list.append(getConfigListEntry(_("VFD led in standby"), config.plugins.VFD_spark.ledMode))

		self["config"].list = self.list
		self["config"].l.setList(self.list)

	def changedEntry(self):
		for x in self.onChangedEntry:
			x()
		self.newConfig()

	def newConfig(self):
		print self["config"].getCurrent()[0]
		if self["config"].getCurrent()[0] == _('VFD text'):
			self.createSetup()

	def abort(self):
		print "aborting"

	def save(self):
		for x in self["config"].list:
			x[1].save()

		configfile.save()
		initVFD()
		self.close()

	def cancel(self):
		initVFD()
		for x in self["config"].list:
			x[1].cancel()
		self.close()

	def Update(self):
		self.createSetup()
		initVFD()

class VFD_Spark:
	def __init__(self, session):
		print "[VFD-SPARK] initializing"
		self.session = session
		self.service = None
		self.onClose = [ ]

		self.Console = Console()

		initVFD()

		global ChannelnumberInstance
		if ChannelnumberInstance is None:
			ChannelnumberInstance = Channelnumber(session)

	def shutdown(self):
		self.abort()

	def abort(self):
		print "[VFD-SPARK] aborting"
		
	config.misc.standbyCounter.addNotifier(standbyCounterChanged, initial_call = False)

def main(menuid):
	if menuid != "system":
		return [ ]
	return [(_("VFD_Spark"), startVFD, "VFD_Spark", None)]

def startVFD(session, **kwargs):
	session.open(VFD_SparkSetup)

sparkVfd = None
gReason = -1
mySession = None

def controlsparkVfd():
	global sparkVfd
	global gReason
	global mySession

	if gReason == 0 and mySession != None and sparkVfd == None:
		print "[VFD-SPARK] Starting !!"
		sparkVfd = VFD_Spark(mySession)
	elif gReason == 1 and sparkVfd != None:
		print "[VFD-SPARK] Stopping !!"

		sparkVfd = None

def sessionstart(reason, **kwargs):
	print "[VFD-SPARK] sessionstart"
	global sparkVfd
	global gReason
	global mySession

	if kwargs.has_key("session"):
		mySession = kwargs["session"]
	else:
		gReason = reason
	controlsparkVfd()

def Plugins(**kwargs):
 	return [ PluginDescriptor(where=[PluginDescriptor.WHERE_AUTOSTART, PluginDescriptor.WHERE_SESSIONSTART], fnc=sessionstart),
 		PluginDescriptor(name="VFD Spark", description="Change VFD display settings",where = PluginDescriptor.WHERE_MENU, fnc = main) ]

