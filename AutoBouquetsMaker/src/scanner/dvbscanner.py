from .. import log
import dvbreader
import datetime
import time

class DvbScanner():
	TIMEOUT_SEC = 20

	VIDEO_ALLOWED_TYPES = [1, 4, 5, 17, 22, 24, 25, 27, 135]
	AUDIO_ALLOWED_TYPES = [2, 10]
	INTERACTIVE_ALLOWED_TYPES = [133]

	def __init__(self):
		self.adapter = 0
		self.demuxer = 0
		self.demuxer_device = "/dev/dvb/adapter0/demux0"
		self.frontend = 0
		self.nit_pid = 0x10
		self.nit_current_table_id = 0x40
		self.nit_other_table_id = 0x41
		self.sdt_pid = 0x11
		self.sdt_current_table_id = 0x42
		self.sdt_other_table_id = 0x46
		self.bat_pid = 0x11
		self.bat_table_id = 0x4a
		self.fastscan_pid = 0x00
		self.fastscan_table_id = 0x00

	def isValidOnidTsid(self, orbital_position, onid, tsid):
		if onid == 0x00 or onid == 0x1111:
			return False
		elif onid == 0x13e:
			return orbital_position != 130 or tsid != 0x578
		elif onid == 0x01:
			return orbital_position == 192
		elif onid == 0x00b1:
			return tsid != 0x00b0
		elif onid == 0x0002:
			return abs(orbital_position - 282) < 6 and tsid != 2019
		elif onid == 0x2000:
			return tsid != 0x1000
		elif onid == 0x5e:
			return abs(orbital_position - 48) < 3 and tsid != 1
		elif onid == 10100:
			return orbital_position != 360 or tsid != 10187
		elif onid == 42:
			return orbital_position != 420 or (tsid != 8 and tsid != 5 and tsid != 2 and tsid != 55)
		elif onid == 100:
			return (orbital_position != 685 and orbital_position != 3560) or tsid != 1
		elif onid == 70:
			return abs(orbital_position - 3592) < 3 and tsid != 46
		elif onid == 30:
			return orbital_position != 3195 or tsid != 21

		return onid < 0xff00

	def setAdapter(self, id):
		self.adapter = id
		self.demuxer_device = "/dev/dvb/adapter%d/demux%d" % (self.adapter, self.demuxer)
		print>>log, "[DvbScanner] Adapter %d" % self.adapter

	def setDemuxer(self, id):
		self.demuxer = id
		self.demuxer_device = "/dev/dvb/adapter%d/demux%d" % (self.adapter, self.demuxer)
		print>>log, "[DvbScanner] Demuxer %d" % self.demuxer

	def setFrontend(self, id):
		self.frontend = id
		print>>log, "[DvbScanner] Frontend %d" % self.frontend

	def setDVBType(self, id):
		self.dvbtype = id
		print>>log, "[DvbScanner] DVBType %s" % self.dvbtype

	def setNitPid(self, value):
		self.nit_pid = value
		print>>log, "[DvbScanner] NIT pid: 0x%x" % self.nit_pid

	def setNitCurrentTableId(self, value):
		self.nit_current_table_id = value
		print>>log, "[DvbScanner] NIT current table id: 0x%x" % self.nit_current_table_id

	def setNitOtherTableId(self, value):
		self.nit_other_table_id = value
		print>>log, "[DvbScanner] NIT other table id: 0x%x" % self.nit_other_table_id

	def setSdtPid(self, value):
		self.sdt_pid = value
		print>>log, "[DvbScanner] SDT pid: 0x%x" % self.sdt_pid

	def setSdtCurrentTableId(self, value):
		self.sdt_current_table_id = value
		print>>log, "[DvbScanner] SDT current table id: 0x%x" % self.sdt_current_table_id

	def setSdtOtherTableId(self, value):
		self.sdt_other_table_id = value
		print>>log, "[DvbScanner] SDT other table id: 0x%x" % self.sdt_other_table_id

	def setBatPid(self, value):
		self.bat_pid = value
		print>>log, "[DvbScanner] BAT pid: 0x%x" % self.bat_pid

	def setBatTableId(self, value):
		self.bat_table_id = value
		print>>log, "[DvbScanner] BAT table id: 0x%x" % self.bat_table_id

	def setFastscanPid(self, value):
		self.fastscan_pid = value
		print>>log, "[DvbScanner] Fastscan pid: 0x%x" % self.fastscan_pid

	def setFastscanTableId(self, value):
		self.fastscan_table_id = value
		print>>log, "[DvbScanner] Fastscan table id: 0x%x" % self.fastscan_table_id

	def buildNamespace(self, transponder):
		orbital_position = transponder['orbital_position']

		namespace = orbital_position << 16
		namespace |= ((transponder['frequency'] / 1000) & 0xFFFF) | ((transponder['polarization'] & 1) << 15)
		if self.isValidOnidTsid(orbital_position, transponder['original_network_id'], transponder['transport_stream_id']):
			namespace &= ~0xFFFF

		return namespace

	def updateTransponders(self, transponders, read_other_section = False, netid = None, bouquettype = None):
		print>>log, "[DvbScanner] Reading transponders..."

		if self.nit_other_table_id == 0x00:
			mask = 0xff
		else:
			mask = self.nit_current_table_id ^ self.nit_other_table_id ^ 0xff

		print>>log, "[DvbScanner] demuxer_device", str(self.demuxer_device)
		print>>log, "[DvbScanner] nit_pid", str(self.nit_pid)
		print>>log, "[DvbScanner] nit_current_table_id", str(self.nit_current_table_id)
		print>>log, "[DvbScanner] mask", str(mask)
		print>>log, "[DvbScanner] frontend", str(self.frontend)
		fd = dvbreader.open(self.demuxer_device, self.nit_pid, self.nit_current_table_id, mask, self.frontend)
		if fd < 0:
			print>>log, "[DvbScanner] Cannot open the demuxer"
			return None

		nit_current_section_version = -1
		nit_current_section_network_id = -1
		nit_current_sections_read = []
		nit_current_sections_count = 0
		nit_current_content = []
		nit_current_completed = False

		nit_other_section_version = -1
		nit_other_section_network_id = -1
		nit_other_sections_read = []
		nit_other_sections_count = 0
		nit_other_content = []
		nit_other_completed = not read_other_section or self.nit_other_table_id == 0x00

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, self.TIMEOUT_SEC)
		while True:
			if datetime.datetime.now() > timeout:
				print>>log, "[DvbScanner] Timed out"
				break

			section = dvbreader.read_nit(fd, self.nit_current_table_id, self.nit_other_table_id)
			if section is None:
				time.sleep(0.1)	# no data.. so we wait a bit
				continue


			if (section["header"]["table_id"] == self.nit_current_table_id 
				and self.dvbtype != 'dvbc' and not nit_current_completed):
				if (section["header"]["version_number"] != nit_current_section_version or section["header"]["network_id"] != nit_current_section_network_id):
					nit_current_section_version = section["header"]["version_number"]
					nit_current_section_network_id = section["header"]["network_id"]
					nit_current_sections_read = []
					nit_current_content = []
					nit_current_sections_count = section["header"]["last_section_number"] + 1

				if section["header"]["section_number"] not in nit_current_sections_read:
					nit_current_sections_read.append(section["header"]["section_number"])
					nit_current_content += section["content"]

					if len(nit_current_sections_read) == nit_current_sections_count:
						nit_current_completed = True
					
			elif (str(section["header"]["network_id"]) == str(netid) and self.dvbtype == 'dvbc' and not nit_current_completed):
				if (section["header"]["version_number"] != nit_current_section_version or section["header"]["network_id"] != nit_current_section_network_id):
					nit_current_section_version = section["header"]["version_number"]
					nit_current_section_network_id = section["header"]["network_id"]
					nit_current_sections_read = []
					nit_current_content = []
					nit_current_sections_count = section["header"]["last_section_number"] + 1
					
				if section["header"]["section_number"] not in nit_current_sections_read:
					nit_current_sections_read.append(section["header"]["section_number"])
					nit_current_content += section["content"]
					
					if len(nit_current_sections_read) == nit_current_sections_count:
						nit_current_completed = True
						nit_other_completed = True


			elif section["header"]["table_id"] == self.nit_other_table_id and not nit_other_completed:
				if (section["header"]["version_number"] != nit_other_section_version or section["header"]["network_id"] != nit_other_section_network_id):
					nit_other_section_version = section["header"]["version_number"]
					nit_other_section_network_id = section["header"]["network_id"]
					nit_other_sections_read = []
					nit_other_content = []
					nit_other_sections_count = section["header"]["last_section_number"] + 1

				if section["header"]["section_number"] not in nit_other_sections_read:
					nit_other_sections_read.append(section["header"]["section_number"])
					nit_other_content += section["content"]

					if len(nit_other_sections_read) == nit_other_sections_count:
						nit_other_completed = True

			if nit_current_completed and nit_other_completed:
				print>>log, "[DvbScanner] Scan complete, netid: ", str(netid)
				break

		dvbreader.close(fd)

		nit_content = nit_current_content
		nit_content += nit_other_content

		transport_stream_id_list = []
		logical_channel_number_dict = {}
		logical_channel_number_dict_tmp = {}
		hd_logical_channel_number_dict_tmp = {}
		service_dict_tmp ={}
		transponders_count = 0
		for transponder in nit_content:
			if len(transponder) == 4: # service
				key = "%x:%x:%x" % (transponder["transport_stream_id"], transponder["original_network_id"], transponder["service_id"])
				service_dict_tmp[key] = transponder
				continue
			if len(transponder) == 5: # lcn
				key = "%x:%x:%x" % (transponder["transport_stream_id"], transponder["original_network_id"], transponder["service_id"])
				logical_channel_number_dict_tmp[key] = transponder
				continue
			if len(transponder) == 6: # HD lcn
				key = "%x:%x:%x" % (transponder["transport_stream_id"], transponder["original_network_id"], transponder["service_id"])
				hd_logical_channel_number_dict_tmp[key] = transponder
				continue
			transponder["services"] = {}
			transponder["dvb_type"] = self.dvbtype
			transponder["bouquet_type"] = bouquettype
			
			if transponder["dvb_type"] == 'dvbc': # DVB-C
				transponder["symbol_rate"] = transponder["symbol_rate"] * 100
				transponder["flags"] = 0
				if transponder["fec_inner"] != 15 and transponder["fec_inner"] > 9:
					transponder["fec_inner"] = 0
				transponder["frequency"] = transponder["frequency"] / 10
				transponder["namespace"] = 0xFFFF0000
				transponder["inversion"] = transponder["fec_outer"]
				transponder["modulation_system"] = 0
			elif transponder["dvb_type"] == 'dvbt': # DVB-T
				transponder["namespace"] = 0xEEEE0000
				transponder["frequency"] = transponder["frequency"] * 10
				transponder["inversion"] = 0
				transponder["plpid"] = 0
				transponder["flags"] = 0
				transponder["system"] = 0
			elif transponder["dvb_type"] == 'dvbs': # DVB-S
				transponder["symbol_rate"] = transponder["symbol_rate"] * 100
				transponder["flags"] = 0
				if transponder["fec_inner"] != 15 and transponder["fec_inner"] > 9:
					transponder["fec_inner"] = 0
				transponder["frequency"] = transponder["frequency"] * 10
				orbital_position = ((transponder["orbital_position"] >> 12) & 0x0F) * 1000
				orbital_position += ((transponder["orbital_position"] >> 8) & 0x0F) * 100
				orbital_position += ((transponder["orbital_position"] >> 4) & 0x0F) * 10
				orbital_position += transponder["orbital_position"] & 0x0F
				if orbital_position != 0 and transponder["west_east_flag"] == 0:
					orbital_position = 3600 - orbital_position
				transponder["orbital_position"] = orbital_position
				transponder["pilot"] = 2

				if transponder["modulation_system"] == 0 and transponder["modulation_type"] == 2:
					transponder["modulation_type"] = 1
				transponder["inversion"] = 2
				transponder["namespace"] = self.buildNamespace(transponder)

			key = "%x:%x:%x" % (transponder["namespace"],
				transponder["transport_stream_id"],
				transponder["original_network_id"])

			if key in transponders:
				transponder["services"] = transponders[key]["services"]
			transponders[key] = transponder
			transponders_count += 1

			if transponder["transport_stream_id"] not in transport_stream_id_list:
				transport_stream_id_list.append(transponder["transport_stream_id"])

		if read_other_section:
			print>>log, "[DvbScanner] Added/Updated %d transponders with network_id = 0x%x and network_id = 0x%x" % (transponders_count, nit_current_section_network_id, nit_other_section_network_id)
		else:
			print>>log, "[DvbScanner] Added/Updated %d transponders with network_id = 0x%x" % (transponders_count, nit_current_section_network_id)

		if len(hd_logical_channel_number_dict_tmp) > 0 and bouquettype == 'hd':
			for id in logical_channel_number_dict_tmp:
				if id in hd_logical_channel_number_dict_tmp:
					lcntofind = hd_logical_channel_number_dict_tmp[id]["logical_channel_number"]
					lcnreplace = logical_channel_number_dict_tmp[id]["logical_channel_number"]
					for id2 in logical_channel_number_dict_tmp:
						if logical_channel_number_dict_tmp[id2]["logical_channel_number"] == lcntofind:
							logical_channel_number_dict[id] = logical_channel_number_dict_tmp[id2]
							logical_channel_number_dict[id]["logical_channel_number"] = lcnreplace
					logical_channel_number_dict[id] = hd_logical_channel_number_dict_tmp[id]
				else:
					logical_channel_number_dict[id] = logical_channel_number_dict_tmp[id]
		else:
			for id in logical_channel_number_dict_tmp:
				logical_channel_number_dict[id] = logical_channel_number_dict_tmp[id]

		return {
			"transport_stream_id_list": transport_stream_id_list,
			"logical_channel_number_dict": logical_channel_number_dict,
			"service_dict_tmp": service_dict_tmp
		}

	def updateAndReadServicesLCN(self, namespace, transponders, servicehacks, transport_stream_id_list, logical_channel_number_dict, service_dict_tmp):
		print>>log, "[DvbScanner] Reading services..."

		if self.sdt_other_table_id == 0x00:
			mask = 0xff
		else:
			mask = self.sdt_current_table_id ^ self.sdt_other_table_id ^ 0xff

		fd = dvbreader.open(self.demuxer_device, self.sdt_pid, self.sdt_current_table_id, mask, self.frontend)
		if fd < 0:
			print>>log, "[DvbScanner] Cannot open the demuxer"
			return None

		sdt_secions_status = {}
		for transport_stream_id in transport_stream_id_list:
			sdt_secions_status[transport_stream_id] = {}
			sdt_secions_status[transport_stream_id]["section_version"] = -1
			sdt_secions_status[transport_stream_id]["sections_read"] = []
			sdt_secions_status[transport_stream_id]["sections_count"] = 0
			sdt_secions_status[transport_stream_id]["content"] = []

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, self.TIMEOUT_SEC)
		while True:
			if datetime.datetime.now() > timeout:
				print>>log, "[DvbScanner] Timed out"
				break

			section = dvbreader.read_sdt(fd, self.sdt_current_table_id, self.sdt_other_table_id)
			if section is None:
				time.sleep(0.1)	# no data.. so we wait a bit
				continue

			if section["header"]["table_id"] == self.sdt_current_table_id or section["header"]["table_id"] == self.sdt_other_table_id:
				if section["header"]["transport_stream_id"] not in transport_stream_id_list:
					continue

				transport_stream_id = section["header"]["transport_stream_id"]
				if section["header"]["version_number"] != sdt_secions_status[transport_stream_id]["section_version"]:
					sdt_secions_status[transport_stream_id]["section_version"] = section["header"]["version_number"]
					sdt_secions_status[transport_stream_id]["sections_read"] = []
					sdt_secions_status[transport_stream_id]["content"] = []
					sdt_secions_status[transport_stream_id]["sections_count"] = section["header"]["last_section_number"] + 1

				if section["header"]["section_number"] not in sdt_secions_status[transport_stream_id]["sections_read"]:
					sdt_secions_status[transport_stream_id]["sections_read"].append(section["header"]["section_number"])
					sdt_secions_status[transport_stream_id]["content"] += section["content"]

					if len(sdt_secions_status[transport_stream_id]["sections_read"]) == sdt_secions_status[transport_stream_id]["sections_count"]:
						transport_stream_id_list.remove(transport_stream_id)

			if len(transport_stream_id_list) == 0:
				break

		if len(transport_stream_id_list) > 0:
			print>>log, "[DvbScanner] Cannot fetch SDT for the following transport_stream_id list: ", transport_stream_id_list

		dvbreader.close(fd)

		service_count = 0
		tmp_services_dict = {}
		for key in sdt_secions_status:
			for section in sdt_secions_status[key]["content"]:
				service = section

				key = "%x:%x:%x" % (service["transport_stream_id"], service["original_network_id"], service["service_id"])


				if logical_channel_number_dict and (key not in logical_channel_number_dict or logical_channel_number_dict[key]["visible_service_flag"] == 0):
					continue
				if service_dict_tmp and key not in service_dict_tmp:
					continue

				service["namespace"] = namespace
				service["flags"] = 0

				if not logical_channel_number_dict:
					service["number"] = service["logical_channel_number"]
					if service["service_type"] == 1 and (service["service_group_id"] == 17 or service["service_group_id"] == 21):
						service["service_type"] = 17
				else:
					service["number"] = logical_channel_number_dict[key]["logical_channel_number"]

				if key in tmp_services_dict:
					tmp_services_dict[key]["numbers"].append(service["number"])
				else:
					service["numbers"] = [service["number"]]
					tmp_services_dict[key] = service

				service_count += 1

		print>>log, "[DvbScanner] Read %d services" % service_count

		video_services = {}
		radio_services = {}

		service_extra_count = 0

		for key in tmp_services_dict:
			service = tmp_services_dict[key]

			if len(servicehacks) > 0:
				skip = False
				exec(servicehacks)

				if skip:
					continue

			tpkey = "%x:%x:%x" % (service["namespace"], service["transport_stream_id"], service["original_network_id"])
			if tpkey not in transponders:
				continue


			transponders[tpkey]["services"][service["service_id"]] = service
			service_extra_count += 1

			if service["service_type"] in DvbScanner.VIDEO_ALLOWED_TYPES or service["service_type"] in DvbScanner.INTERACTIVE_ALLOWED_TYPES:
				for number in service["numbers"]:
					if number not in video_services:
						video_services[number] = service
			else:
				for number in service["numbers"]:
					if number not in radio_services:
						radio_services[number] = service

		print>>log, "[DvbScanner] %d valid services" % service_extra_count
		return {
			"video": video_services,
			"radio": radio_services
		}

	def updateAndReadServicesFastscan(self, namespace, transponders, servicehacks, transport_stream_id_list, logical_channel_number_dict):
		print>>log, "[DvbScanner] Reading services..."

		fd = dvbreader.open(self.demuxer_device, self.fastscan_pid, self.fastscan_table_id, 0xff, self.frontend)
		if fd < 0:
			print>>log, "[DvbScanner] Cannot open the demuxer"
			return None

		fastscan_section_version = -1
		fastscan_section_id = -1
		fastscan_sections_read = []
		fastscan_sections_count = 0
		fastscan_content = []

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, self.TIMEOUT_SEC)
		while True:
			if datetime.datetime.now() > timeout:
				print>>log, "[DvbScanner] Timed out"
				break

			section = dvbreader.read_fastscan(fd, self.fastscan_table_id)
			if section is None:
				time.sleep(0.1)	# no data.. so we wait a bit
				continue

			if section["header"]["table_id"] == self.fastscan_table_id:
				if (section["header"]["version_number"] != fastscan_section_version
					or section["header"]["fastscan_id"] != fastscan_section_id):

					fastscan_section_version = section["header"]["version_number"]
					fastscan_section_id = section["header"]["fastscan_id"]
					fastscan_sections_read = []
					fastscan_content = []
					fastscan_sections_count = section["header"]["last_section_number"] + 1

				if section["header"]["section_number"] not in fastscan_sections_read:
					fastscan_sections_read.append(section["header"]["section_number"])
					fastscan_content += section["content"]

					if len(fastscan_sections_read) == fastscan_sections_count:
						break

		dvbreader.close(fd)

		service_count = 0
		tmp_services_dict = {}
		for section in fastscan_content:
			service = section

			key = "%x:%x:%x" % (service["transport_stream_id"], service["original_network_id"], service["service_id"])

			if key not in logical_channel_number_dict:
				continue

			if logical_channel_number_dict[key]["visible_service_flag"] == 0:
				continue

			service["free_ca"] = 1
			service["namespace"] = namespace
			service["flags"] = 0
			service["number"] = logical_channel_number_dict[key]["logical_channel_number"]

			if key in tmp_services_dict:
				tmp_services_dict[key]["numbers"].append(service["number"])
			else:
				service["numbers"] = [service["number"]]
				tmp_services_dict[key] = service
				
			service_count += 1

		print>>log, "[DvbScanner] Read %d services" % service_count

		video_services = {}
		radio_services = {}

		service_extra_count = 0

		for key in tmp_services_dict:
			service = tmp_services_dict[key]

			if len(servicehacks) > 0:
				skip = False
				exec(servicehacks)

				if skip:
					continue

			tpkey = "%x:%x:%x" % (service["namespace"], service["transport_stream_id"], service["original_network_id"])
			if tpkey not in transponders:
				continue


			transponders[tpkey]["services"][service["service_id"]] = service
			service_extra_count += 1

			if service["service_type"] in DvbScanner.VIDEO_ALLOWED_TYPES or service["service_type"] in DvbScanner.INTERACTIVE_ALLOWED_TYPES:
				for number in service["numbers"]:
					if number not in video_services:
						video_services[number] = service
			else:
				for number in service["numbers"]:
					if number not in radio_services:
						radio_services[number] = service

		print>>log, "[DvbScanner] %d valid services" % service_extra_count
		return {
			"video": video_services,
			"radio": radio_services
		}

	def updateAndReadServicesSKY(self, bouquet_id, region_id, namespace, transponders, servicehacks):
		print>>log, "[DvbScanner] Reading services..."

		fd = dvbreader.open(self.demuxer_device, self.bat_pid, self.bat_table_id, 0xff, self.frontend)
		if fd < 0:
			print>>log, "[DvbScanner] Cannot open the demuxer"
			return None

		bat_section_version = -1
		bat_sections_read = []
		bat_sections_count = 0
		bat_content = []

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, self.TIMEOUT_SEC)
		while True:
			if datetime.datetime.now() > timeout:
				print>>log, "[DvbScanner] Timed out"
				break

			section = dvbreader.read_bat(fd, self.bat_table_id)
			if section is None:
				time.sleep(0.1)	# no data.. so we wait a bit
				continue

			if section["header"]["table_id"] == self.bat_table_id:
				if section["header"]["bouquet_id"] != bouquet_id:
					continue

				if section["header"]["version_number"] != bat_section_version:
					bat_section_version = section["header"]["version_number"]
					bat_sections_read = []
					bat_content = []
					bat_sections_count = section["header"]["last_section_number"] + 1

				if section["header"]["section_number"] not in bat_sections_read:
					bat_sections_read.append(section["header"]["section_number"])
					bat_content += section["content"]

					if len(bat_sections_read) == bat_sections_count:
						break

		dvbreader.close(fd)

		service_count = 0
		transport_stream_id_list = []
		tmp_services_dict = {}
		for service in bat_content:
			if service["descriptor_tag"] != 0xb1:
				continue
				
			if service["region_id"] != region_id and service["region_id"] != 0xff:
				continue

			if service["service_type"] not in DvbScanner.VIDEO_ALLOWED_TYPES and service["service_type"] not in DvbScanner.AUDIO_ALLOWED_TYPES and service["service_type"] not in DvbScanner.INTERACTIVE_ALLOWED_TYPES:
				continue

			if service["service_type"] == 0x05:
				service["service_type"] = 0x01;		# enigma2 doesn't like 0x05 VOD
				
			service["free_ca"] = 1
			service["service_name"] = "Unknown"
			service["provider_name"] = "Unknown"
			service["namespace"] = namespace
			service["flags"] = 0

			key = "%x:%x:%x" % (service["transport_stream_id"], service["original_network_id"], service["service_id"])
			if key in tmp_services_dict:
				tmp_services_dict[key]["numbers"].append(service["number"])
			else:
				service["numbers"] = [service["number"]]
				tmp_services_dict[key] = service

			service_count += 1

			if service["transport_stream_id"] not in transport_stream_id_list:
				transport_stream_id_list.append(service["transport_stream_id"])

		print>>log, "[DvbScanner] Read %d services with bouquet_id = 0x%x" % (service_count, bouquet_id)

		print>>log, "[DvbScanner] Reading services extra info..."

		if self.sdt_other_table_id == 0x00:
			mask = 0xff
		else:
			mask = self.sdt_current_table_id ^ self.sdt_other_table_id ^ 0xff

		fd = dvbreader.open(self.demuxer_device, self.sdt_pid, self.sdt_current_table_id, mask, self.frontend)
		if fd < 0:
			print>>log, "[DvbScanner] Cannot open the demuxer"
			return None

		sdt_secions_status = {}
		for transport_stream_id in transport_stream_id_list:
			sdt_secions_status[transport_stream_id] = {}
			sdt_secions_status[transport_stream_id]["section_version"] = -1
			sdt_secions_status[transport_stream_id]["sections_read"] = []
			sdt_secions_status[transport_stream_id]["sections_count"] = 0
			sdt_secions_status[transport_stream_id]["content"] = []

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, self.TIMEOUT_SEC)
		while True:
			if datetime.datetime.now() > timeout:
				print>>log, "[DvbScanner] Timed out"
				break

			section = dvbreader.read_sdt(fd, self.sdt_current_table_id, self.sdt_other_table_id)
			if section is None:
				time.sleep(0.1)	# no data.. so we wait a bit
				continue

			if section["header"]["table_id"] == self.sdt_current_table_id or section["header"]["table_id"] == self.sdt_other_table_id:
				if section["header"]["transport_stream_id"] not in transport_stream_id_list:
					continue

				transport_stream_id = section["header"]["transport_stream_id"]
				if section["header"]["version_number"] != sdt_secions_status[transport_stream_id]["section_version"]:
					sdt_secions_status[transport_stream_id]["section_version"] = section["header"]["version_number"]
					sdt_secions_status[transport_stream_id]["sections_read"] = []
					sdt_secions_status[transport_stream_id]["content"] = []
					sdt_secions_status[transport_stream_id]["sections_count"] = section["header"]["last_section_number"] + 1

				if section["header"]["section_number"] not in sdt_secions_status[transport_stream_id]["sections_read"]:
					sdt_secions_status[transport_stream_id]["sections_read"].append(section["header"]["section_number"])
					sdt_secions_status[transport_stream_id]["content"] += section["content"]

					if len(sdt_secions_status[transport_stream_id]["sections_read"]) == sdt_secions_status[transport_stream_id]["sections_count"]:
						transport_stream_id_list.remove(transport_stream_id)

			if len(transport_stream_id_list) == 0:
				break

		if len(transport_stream_id_list) > 0:
			print>>log, "[DvbScanner] Cannot fetch SDT for the following transport_stream_id list: ", transport_stream_id_list

		dvbreader.close(fd)

		for key in sdt_secions_status:
			for section in sdt_secions_status[key]["content"]:
				srvkey = "%x:%x:%x" % (section["transport_stream_id"], section["original_network_id"], section["service_id"])

				if srvkey not in tmp_services_dict:
					continue

				service = tmp_services_dict[srvkey]

				service["free_ca"] = section["free_ca"]
				service["service_name"] = section["service_name"]
				service["provider_name"] = section["provider_name"]

		video_services = {}
		radio_services = {}

		service_extra_count = 0

		for key in tmp_services_dict:
			service = tmp_services_dict[key]

			if len(servicehacks) > 0:
				skip = False
				exec(servicehacks)

				if skip:
					continue

			tpkey = "%x:%x:%x" % (service["namespace"], service["transport_stream_id"], service["original_network_id"])
			if tpkey not in transponders:
				continue


			transponders[tpkey]["services"][service["service_id"]] = service
			service_extra_count += 1

			if service["service_type"] in DvbScanner.VIDEO_ALLOWED_TYPES or service["service_type"] in DvbScanner.INTERACTIVE_ALLOWED_TYPES:
				for number in service["numbers"]:
					if service["region_id"] == 0xff:
						if number not in video_services:
							video_services[number] = service
					else:
						video_services[number] = service
			else:
				for number in service["numbers"]:
					if number not in radio_services:
						radio_services[number] = service


		print>>log, "[DvbScanner] Read extra info for %d services" % service_extra_count
		return {
			"video": video_services,
			"radio": radio_services
		}
		
	def updateAndReadServicesFreeSat(self, bouquet_id, region_id, namespace, transponders, servicehacks):
		print>>log, "[DvbScanner] Reading services..."

		fd = dvbreader.open(self.demuxer_device, self.bat_pid, self.bat_table_id, 0xff, self.frontend)
		if fd < 0:
			print>>log, "[DvbScanner] Cannot open the demuxer"
			return None

		bat_section_version = -1
		bat_sections_read = []
		bat_sections_count = 0
		bat_content = []

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, self.TIMEOUT_SEC)
		while True:
			if datetime.datetime.now() > timeout:
				print>>log, "[DvbScanner] Timed out"
				break

			section = dvbreader.read_bat(fd, self.bat_table_id)
			if section is None:
				time.sleep(0.1)	# no data.. so we wait a bit
				continue

			if section["header"]["table_id"] == self.bat_table_id:
				if section["header"]["bouquet_id"] != bouquet_id:
					continue

				if section["header"]["version_number"] != bat_section_version:
					bat_section_version = section["header"]["version_number"]
					bat_sections_read = []
					bat_content = []
					bat_sections_count = section["header"]["last_section_number"] + 1

				if section["header"]["section_number"] not in bat_sections_read:
					bat_sections_read.append(section["header"]["section_number"])
					bat_content += section["content"]

					if len(bat_sections_read) == bat_sections_count:
						break

		dvbreader.close(fd)

		service_count = 0
		transport_stream_id_list = []
		tmp_services_dict = {}
		
		for service in bat_content:
			if service["descriptor_tag"] != 0xd3:
				continue
				
			if service["region_id"] != region_id and service["region_id"] != 0xffff:
				continue

			service["service_type"] = 1
			service["free_ca"] = 1
			service["service_name"] = "Unknown"
			service["provider_name"] = "Unknown"
			service["namespace"] = namespace
			service["flags"] = 0
			
			key = "%x:%x:%x" % (service["transport_stream_id"], service["original_network_id"], service["service_id"])
			if key in tmp_services_dict:
				tmp_services_dict[key]["numbers"].append(service["number"])
			else:
				service["numbers"] = [service["number"]]
				tmp_services_dict[key] = service

			service_count += 1

			if service["transport_stream_id"] not in transport_stream_id_list:
				transport_stream_id_list.append(service["transport_stream_id"])

		for service in bat_content:
			if service["descriptor_tag"] != 0x41:
				continue
				
			if service["service_type"] not in DvbScanner.VIDEO_ALLOWED_TYPES and service["service_type"] not in DvbScanner.AUDIO_ALLOWED_TYPES and service["service_type"] not in DvbScanner.INTERACTIVE_ALLOWED_TYPES:
				continue

			if service["service_type"] == 0x05:
				service["service_type"] = 0x01;		# enigma2 doesn't like 0x05 VOD

			key = "%x:%x:%x" % (service["transport_stream_id"], service["original_network_id"], service["service_id"])
			if key in tmp_services_dict:
				tmp_services_dict[key]["service_type"] = service["service_type"]
		
		print>>log, "[DvbScanner] Read %d services with bouquet_id = 0x%x" % (service_count, bouquet_id)
		
		print>>log, "[DvbScanner] Reading services extra info..."

		#Clear double services values
		for key in tmp_services_dict:
			if len(tmp_services_dict[key]["numbers"]) > 1:
				tmp_services_dict[key]["numbers"][0] = tmp_services_dict[key]["numbers"][1]
				tmp_services_dict[key]["number"] = tmp_services_dict[key]["numbers"][1]
				del tmp_services_dict[key]["numbers"][1]
				
		if self.sdt_other_table_id == 0x00:
			mask = 0xff
		else:
			mask = self.sdt_current_table_id ^ self.sdt_other_table_id ^ 0xff

		fd = dvbreader.open(self.demuxer_device, self.sdt_pid, self.sdt_current_table_id, mask, self.frontend)
		if fd < 0:
			print>>log, "[DvbScanner] Cannot open the demuxer"
			return None

		sdt_secions_status = {}
		for transport_stream_id in transport_stream_id_list:
			sdt_secions_status[transport_stream_id] = {}
			sdt_secions_status[transport_stream_id]["section_version"] = -1
			sdt_secions_status[transport_stream_id]["sections_read"] = []
			sdt_secions_status[transport_stream_id]["sections_count"] = 0
			sdt_secions_status[transport_stream_id]["content"] = []

		timeout = datetime.datetime.now()
		timeout += datetime.timedelta(0, self.TIMEOUT_SEC)
		while True:
			if datetime.datetime.now() > timeout:
				print>>log, "[DvbScanner] Timed out"
				break

			section = dvbreader.read_sdt(fd, self.sdt_current_table_id, self.sdt_other_table_id)
			if section is None:
				time.sleep(0.1)	# no data.. so we wait a bit
				continue

			if section["header"]["table_id"] == self.sdt_current_table_id or section["header"]["table_id"] == self.sdt_other_table_id:
				if section["header"]["transport_stream_id"] not in transport_stream_id_list:
					continue

				transport_stream_id = section["header"]["transport_stream_id"]
				if section["header"]["version_number"] != sdt_secions_status[transport_stream_id]["section_version"]:
					sdt_secions_status[transport_stream_id]["section_version"] = section["header"]["version_number"]
					sdt_secions_status[transport_stream_id]["sections_read"] = []
					sdt_secions_status[transport_stream_id]["content"] = []
					sdt_secions_status[transport_stream_id]["sections_count"] = section["header"]["last_section_number"] + 1

				if section["header"]["section_number"] not in sdt_secions_status[transport_stream_id]["sections_read"]:
					sdt_secions_status[transport_stream_id]["sections_read"].append(section["header"]["section_number"])
					sdt_secions_status[transport_stream_id]["content"] += section["content"]

					if len(sdt_secions_status[transport_stream_id]["sections_read"]) == sdt_secions_status[transport_stream_id]["sections_count"]:
						transport_stream_id_list.remove(transport_stream_id)

			if len(transport_stream_id_list) == 0:
				break

		if len(transport_stream_id_list) > 0:
			print>>log, "[DvbScanner] Cannot fetch SDT for the following transport_stream_id list: ", transport_stream_id_list

		dvbreader.close(fd)

		for key in sdt_secions_status:
			for section in sdt_secions_status[key]["content"]:
				srvkey = "%x:%x:%x" % (section["transport_stream_id"], section["original_network_id"], section["service_id"])

				if srvkey not in tmp_services_dict:
					continue

				service = tmp_services_dict[srvkey]

				service["free_ca"] = section["free_ca"]
				service["service_name"] = section["service_name"]
				service["provider_name"] = section["provider_name"]

		video_services = {}
		radio_services = {}

		service_extra_count = 0

		for key in tmp_services_dict:
			service = tmp_services_dict[key]

			if len(servicehacks) > 0:
				skip = False
				exec(servicehacks)

				if skip:
					continue

			tpkey = "%x:%x:%x" % (service["namespace"], service["transport_stream_id"], service["original_network_id"])
			if tpkey not in transponders:
				continue


			transponders[tpkey]["services"][service["service_id"]] = service
			service_extra_count += 1

			if service["service_type"] in DvbScanner.VIDEO_ALLOWED_TYPES or service["service_type"] in DvbScanner.INTERACTIVE_ALLOWED_TYPES:
				for number in service["numbers"]:
					if service["region_id"] == 0xffff:
						if number not in video_services:
							video_services[number] = service
					else:
						video_services[number] = service
			else:
				for number in service["numbers"]:
					if number not in radio_services:
						radio_services[number] = service


		print>>log, "[DvbScanner] Read extra info for %d services" % service_extra_count
		return {
			"video": video_services,
			"radio": radio_services
		}
