import time

from openerp import tools
from openerp import _, api, fields, models
import openerp.addons.decimal_precision as dp
from openerp.tools.translate import _
from datetime import datetime, timedelta
import logging

class membership_booking(models.Model):
	_name = "membership_lite.booking"

	def make_long_booking( self, cr, uid, vals, context= None):
		_logger = logging.getLogger(__name__)
		if 'long' not in vals:
			return {'error': 'Prenotazione lunga fallita'}

		date = vals['date'] if 'date' in vals else None
		dates = []

		lb_ids = self.pool.get('membership_lite.long_booking').search(cr, uid, [], context=None)
		if not lb_ids:
			return {'Error': 'No long term booking rules defined'}
		lbs =  self.pool.get('membership_lite.long_booking').browse(cr, uid, lb_ids, context=None)
		lb = lbs[0]

		date_date = datetime.strptime(date, '%Y-%m-%d')
		end_date = date_date + timedelta(days=lb.duration * 365/12)
		_logger.info(date_date)
		_logger.info(end_date)
		current_date = date_date
		while current_date <= end_date:
			dates.append( current_date )
			if lb.xtype == 'giorno':
				current_date = current_date + timedelta(days=1)
				continue
			if lb.xtype == 'settimana':
				current_date = current_date + timedelta(weeks=1)
				continue
			if lb.xtype == 'messe':
				current_date = current_date + timedelta(days=365/12)
				continue

		are_errors = False
		created_ids = []
		for date in dates:
			vals['date'] = date.strftime( '%Y-%m-%d' )
			vals['long'] = 'ignore'
			r = self.make_booking( cr, uid, vals, context=None )
			if 'error' in r:
				are_errors = True
				_logger.info(r)
				break
			created_ids.append(r['tech_id'])

		if are_errors:
			self.pool.get('membership_lite.booking').unlink(cr, uid, created_ids, context=None)
			_logger.info("DELETING")
			return {'error': 'Non è possibile prenotare a lungo termine'}
		_logger.info('SUCCESS %s' % created_ids)

		return {
			'user': '',
			'date': '',
			'from': '',
			'to':'',
			'resource': '',
			'note': "Creata una prenotazione %s da %s a %s" % (lb.xtype, date_date.strftime( '%Y-%m-%d' ), end_date.strftime( '%Y-%m-%d' )),
			'long': 1
		}


	def make_booking( self, cr, uid, vals, context=None ):
		_logger = logging.getLogger(__name__)
		date = vals['date'] if 'date' in vals else None
		resource = vals['resource'] if 'resource' in vals else None
		t_from = vals['from'] if 'from' in vals else None
		t_to = vals['to'] if 'to' in vals else None
		user_id = vals['user'] if 'user' in vals else None
		if 'long' in vals and vals['long'] != 'ignore':
			return {'error': 'Wrong method'}

		if not date or not resource or not t_from or not t_to or not user_id:
			return {'error': 'Incomplete data'}

		resource_id = int(resource)
		resource = self.pool.get('membership_lite.resource').browse(cr, uid, resource_id, context=None)
		if not resource:
			return {'error':'Resource error'}

		t_from = float(t_from)
		t_to = float(t_to)
		user_id = int(user_id)

		user = self.pool.get('res.partner').browse(cr, uid, user_id, context=None)
		if not user:
			return {'error': 'User doesnt exist'}
		user = user[0]

		if not self.pool.get('res.partner').is_included(cr, uid, {'user': user.id, 'resource': resource.id}, context=None):
			return {'error': 'User cannot access the resource or its not available for booking'}

		hours = self.pool.get('membership_lite.resource').get_hours(cr, uid, {'user': user.id, 'date': date, 'resource': resource_id}, context=None)
		if not hours:
			return {'error': 'Failure to retrieve hours!'}
		oh = hours['hours']
		duration = t_to - t_from

		hours_to_check = []
		if duration > 1:
			cnt = t_from
			while cnt <= t_to:
				xstart = cnt
				cnt += 1
				xend = cnt
				hours_to_check.append({'start': xstart, 'end': xend})
		else:
			hours_to_check.append({'start': t_from, 'end': t_to})
		available = True
		for hour in hours_to_check:
			found = False
			for h in oh:
				if hour['start'] >= h['from'] and hour['end'] <= h['to']:
					found = True
					if not h['available']:
						available = False
						break
			if not found:
				available = False
				break
			if not available:
				break
		if not available:
			return {'error': 'This time is not available'}


		transaction_amount = None
		#check member for Payment
		member_status = user.ml_membership_status

		if member_status is not 'free':
			credit_status = user.credit_status
			date_date = datetime.strptime(date, '%Y-%m-%d')
			dow = date_date.weekday()
			price = self.pool.get('membership_lite.price_rule').get_price( cr, uid, {'start': t_from, 'end': t_to, 'dow': dow, 'date': date_date}, context=None)
			if not price:
				return {'error': 'Price couldnt be retrieved'}
			price_for_session = price
			_logger.info("PRICE FOR THIS: %s" % price_for_session)
			if credit_status - price_for_session < 0:
				return {'error': 'Not enough credit for this'}
			#Remove credit from member_id
			purchase_vals = {
				'member': user.id,
				'ml_amount': price_for_session,
				'ml_note': 'Purchase of %sh time for %s' % (duration, resource.name),
				'ml_direction': 'out'
			}
			rc_line = self.pool.get('membership_lite.credit_line').create( cr, uid, purchase_vals, context=None)
			if rc_line:
				transaction_amount = price_for_session
			else:
				return {'error': 'Error in payment'}

		new_vals = {
			'member_id': user_id,
			'day': date,
			'hour_from': t_from,
			'hour_to': t_to,
			'resource_id': resource_id,
			'note': ''
		}
		success = self.create(cr, uid, new_vals, context=None)
		if not success:
			if transaction_amount:
				rolled_back = self.pool.get('membership_lite.credit_line').unlink( cr, uid, rc_line, context=None)
				if not rolled_back:
					self.unlink(cr, uid, success, context=None)
			return {'error': 'La creazione della prenotazione è fallita'}
		new_booking = self.browse( cr, uid, success, context=None)

		return {
			'user': new_booking.member_id.name,
			'date': new_booking.day,
			'from': new_booking.hour_from,
			'to': new_booking.hour_to,
			'resource': new_booking.resource_id.name,
			'note': new_booking.note,
			'tech_id': new_booking.id
		}

	member_id = fields.Many2one( 'res.partner', string="Member", required="1" )
	day = fields.Date( 'Date' )
	hour_from = fields.Float( 'From' )
	hour_to = fields.Float( 'To' )
	resource_id = fields.Many2one('membership_lite.resource', string='Resource', required="1")
	note = fields.Text( 'Note' )
