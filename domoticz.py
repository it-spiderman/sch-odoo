import time

from openerp import tools
from openerp import _, api, fields, models
import openerp.addons.decimal_precision as dp
from openerp.tools.translate import _
from datetime import datetime, timedelta
import logging
import urllib2

class membership_lite_domoticz(models.Model):
	_name = 'membership_lite.domoticz'

	def open_gate( self, cr, uid, vals, context=None ):
		_logger = logging.getLogger(__name__)
		_logger.info(vals);
		if 'rfid' not in vals:
			return {'error': 'No RFID in the request'}

		member_id = self.pool.get('res.partner').search( cr, uid, [('ml_rfid', '=', vals['rfid'])], context=None )
		if not member_id:
			return {'error': 'No member with such RFID'}
		member_id = member_id[0]
		time_now = datetime.now().time()
		date_now = datetime.now().date()
		ftime = float(time_now.minute) * 100 / 60 / 100 + float(time_now.hour)
		date_string = date_now.strftime( '%Y-%m-%d' )
		_logger.info("DATE: %s, time: %s, full:%s" % (date_string, ftime, datetime.now()))
		tz_correct = 2
		ftime += tz_correct
		booking_ids = self.pool.get('membership_lite.booking').search( cr, uid, [('day', '=', date_string), ('member_id', '=', member_id)], context=None)
		bookings = self.pool.get('membership_lite.booking').browse(cr, uid, booking_ids, context=None)
		command = None
		for booking in bookings:
			resource = booking.resource_id
			allow_before = float(resource.allow_access_before) * 100 / 60 / 100
			_logger.info("ALLOW BEFORE: %s - %s" % (ftime, booking.hour_from - allow_before))
			if ftime >= booking.hour_from - allow_before and ftime < booking.hour_to:
				command = booking.resource_id.switch_id.url
				import urllib2, base64

				request = urllib2.Request(command)
				base64string = base64.b64encode('%s:%s' % ('antonio', 'lapenna'))
				request.add_header("Authorization", "Basic %s" % base64string)
				result = urllib2.urlopen(request)
				code = result.getcode()
				_logger.info(code);
				xv = {
					'member_id': booking.member_id.id,
					'resource_id': booking.resource_id.id,
					'booking_id': booking.id,
					'status': str( code )
				}
				access_entry = self.pool.get('membership_lite.domoticz_access').create(cr, uid, xv, context=None)
				if code == 200:
					if not access_entry:
						return {'success': '1', 'warning': 'Gate opened but log not created'}
					return {'success': '1'}
				else:
					if not access_entry:
						return {'success': '0', 'warning': 'Gate not opened and log not created'}
					return {'success': '0'}

		return {'success': '0'}

	name = fields.Char( 'Name' )
	url = fields.Char( 'URL', required=True )
	impuls = fields.Boolean( 'Impuls', help='Give only 1 second impuls' )

class membership_lite_domoticz_access(models.Model):
	_name = 'membership_lite.domoticz_access'

	member_id = fields.Many2one( 'res.partner', string='Member' )
	resource_id = fields.Many2one( 'membership_lite.resource', string='Resource' )
	booking_id = fields.Many2one( 'membership_lite.booking', string='Booking' )
	date = fields.Datetime( string='Date and time', default=datetime.now() )
	status = fields.Selection([('200', 'OK'), ('404', 'Domoticz not found'), ('403', 'Access to domoticz denied'), ('500', 'Internal error on domoticz')], string='Status')
