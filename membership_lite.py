# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import time

from openerp import tools
from openerp import _, api, fields, models
import openerp.addons.decimal_precision as dp
from openerp.tools.translate import _
from datetime import datetime, timedelta
import logging

STATE = [
	('none', 'Non Member'),
	('canceled', 'Cancelled Member'),
	('free', 'Free Member'),
	('paid', 'Paid Member')
]

class membership_profile(models.Model):
	_name = 'membership_lite.membership_profile'

	name = fields.Char( 'Name', required="1")
	desc = fields.Text( 'Description' )
	m_type = fields.Selection([('fixed', 'Fixed'), ('relative', 'Relative')], string="Membership type", default='relative', required="1")
	duration = fields.Integer( 'Duration in days')
	start_date = fields.Date( 'Startdate' )
	end_date = fields.Date( 'Enddate' )
	price = fields.Float( 'Price' )

class membership_line(models.Model):
	_name = 'membership_lite.membership_line'

	@api.onchange( 'ml_profile' )
	def profile_onchange(self):
		profile = self.ml_profile or None
		if profile is None:
			return None

		m_type = profile.m_type
		if m_type == 'relative':
			if not profile.duration:
				return None
			self.ml_start = datetime.today()
			self.ml_end = datetime.today() + timedelta(days=profile.duration)

		if m_type == 'fixed':
			if not profile.end_date:
				return None
			self.ml_start = profile.start_date or fields.Date.today()
			self.ml_end = profile.end_date

		self.ml_price = profile.price



	partner_id = fields.Many2one('res.partner', string='Member')
	date = fields.Date( 'Purchase date', default=fields.Date.today() )
	ml_profile = fields.Many2one('membership_lite.membership_profile',string='Membership profile')
	ml_price = fields.Float('Price')
	ml_start = fields.Date('Membership start')
	ml_end = fields.Date('Membership end')

class credit_line(models.Model):
	_name = 'membership_lite.credit_line'

	member = fields.Many2one('res.partner', string='Member')
	date = fields.Datetime( 'Date', default=fields.Datetime.now())
	ml_amount = fields.Float('Amount', required="1")
	ml_payment_method = fields.Selection([('cash', 'Cash'), ('paypal', 'Paypal')], string="Payment method")
	ml_note = fields.Text('Notes')
	ml_direction = fields.Selection([('in', 'Buy'), ('out', 'Spend')], default="in", required="1", string="Activity")
	ml_transfer_id = fields.Char('Transfer ID')

class Partner(models.Model):
	_inherit = 'res.partner'

	def _get_state(self):
		_logger = logging.getLogger(__name__)
		for member in self:
			if not member.member:
				continue
			#default
			member.ml_membership_status = 'none'

			if member.ml_free_member:
				member.ml_membership_status = 'free'
				break
			m_lines = member.ml_membership_lines
			if not m_lines:
				break
			for line in m_lines:
				today = datetime.today()
				m_start = datetime.strptime(line.ml_start, "%Y-%m-%d")
				m_end = datetime.strptime(line.ml_end, "%Y-%m-%d")
				if m_start <= today and m_end >= today:
					member.ml_membership_status = 'paid'
					break



	def _get_membership_start(self):
		for member in self:
			if not member.member:
				continue
			m_lines = member.ml_membership_lines
			if not m_lines:
				return None
			start = None
			for line in m_lines:
				today = datetime.today()
				m_start = datetime.strptime(line.ml_start, "%Y-%m-%d")
				m_end = datetime.strptime(line.ml_end, "%Y-%m-%d")
				if m_start > today or m_end < today:
					continue
				if not start or m_start < start:
					start = m_start

			member.ml_membership_start = start

	def _get_membership_end(self):
		for member in self:
			if not member.member:
				continue
			m_lines = member.ml_membership_lines
			if not m_lines:
				return None
			end = None
			for line in m_lines:
				today = datetime.today()
				m_start = datetime.strptime(line.ml_start, "%Y-%m-%d")
				m_end = datetime.strptime(line.ml_end, "%Y-%m-%d")
				if m_start > today or m_end < today:
					continue
				if not end or m_end > end:
					end = m_end

			member.ml_membership_end = end

	def _get_credit_status(self):
		for member in self:
			if not member.member:
				continue
			m_cr_lines = member.ml_credit_lines
			if not m_cr_lines:
				member.credit_status = 0
			in_amount = 0
			out_amount = 0
			for line in m_cr_lines:
				if line.ml_direction == 'in':
					in_amount += line.ml_amount

				if line.ml_direction == 'out':
					out_amount += line.ml_amount

			member.credit_status = in_amount - out_amount

	def authenticate_web_user( self, cr, uid, vals, context=None ):
		_logger = logging.getLogger(__name__)
		uname = vals['uname']
		pwd = vals['pass']
		user_id = self.pool.get('res.partner').search(cr, uid, [('member', '=', True), ('ml_web_user', '=', uname), ('ml_web_pass', '=', pwd)], context=context)
		if not user_id:
			user_id = self.pool.get('res.partner').search(cr, uid, [('member', '=', True), ('email', '=', uname), ('ml_web_pass', '=', pwd)], context=context)

		if not user_id:
			return {}

		user = self.pool.get('res.partner').browse(cr, uid, user_id, context=context)
		if not user:
			return {}
		user = user[0]

		return {
			'id': user_id[0],
			'name': user.name,
			'status': user.ml_membership_status,
			'credit': user.credit_status,
			'start': user.ml_membership_start,
			'end': user.ml_membership_end
		}

	def get_info( self, cr, uid, vals, context=None ):
		user_id = vals['user'];
		if not user_id:
			return {'error': 'User is not valid'}

		user = self.browse(cr, uid, user_id, context=None)
		if not user:
			return {'error': 'User is not valid'}
		return {
			'status': user.ml_membership_status,
			'credit': user.credit_status,
			'start': user.ml_membership_start,
			'end': user.ml_membership_end
		}

	def get_profile_info( self, cr, uid, vals, context=None ):
		_logger = logging.getLogger(__name__)
		user = self.pool.get('res.partner').browse( cr, uid, vals['user_id'], context=context )
		if not user:
			return {}
		if type(user) == 'array':
			user = user[0]
		res = {}
		rm_lines = []
		rc_lines = []
		m_lines = user.ml_membership_lines
		c_lines = user.ml_credit_lines

		for line in m_lines:
			rm_lines.append({
				'date': line.date,
				'profile': line.ml_profile.name,
				'price': line.ml_price,
				'start': line.ml_start,
				'end': line.ml_end
			})
		for line in c_lines:
			rc_lines.append({
				'date': line.date,
				'amount': line.ml_amount,
				'method': line.ml_payment_method,
				'direction': 'Buy' if line.ml_direction == 'in' else 'Spend',
				'transfer_id': line.ml_transfer_id,
				'note': line.ml_note,

			})

		res['m_lines'] = rm_lines
		res['c_lines'] = rc_lines
		_logger.info(res);
		return res


	ml_web_user = fields.Char( 'Website username' )
	ml_web_pass = fields.Char( 'Website password' )
	member = fields.Boolean('Is member')
	ml_free_member = fields.Boolean( 'Free member' )
	credit_status = fields.Float(compute='_get_credit_status')
	ml_membership_status = fields.Selection(selection=STATE, compute='_get_state', string='Membership state')
	ml_membership_lines = fields.One2many('membership_lite.membership_line', 'partner_id', string='Membership lines')
	ml_credit_lines = fields.One2many('membership_lite.credit_line', 'member', string='Credit history')
	ml_membership_start = fields.Date('Membership start', compute='_get_membership_start')
	ml_membership_end = fields.Date('Membership end', compute='_get_membership_end')


class membership_resource(models.Model):
	_name = "membership_lite.resource"

	def get_disabled_dates( self, cr, uid, vals, context=False ):
		_logger = logging.getLogger(__name__)
		today = datetime.today().date()

		res = {}
		disabled = []
		res['start_date'] = str(today)
		i = 0
		while i < 30:
			is_open = self.get_global_hours( cr, uid, {'date': str(today)}, context=None)
			if not is_open:
				disabled.append(str(today))
			today = today + timedelta(days=1)
			i += 1
		res['end_date'] = str(today)
		res['disabled'] = disabled
		_logger.info(res)

		return res

	def get_global_hours( self, cr, uid, vals, context=False):
		date_str = vals['date']
		date = datetime.strptime(date_str, '%Y-%m-%d')
		dow = date.weekday()
		is_open = True
		oh_ids = self.pool.get('membership_lite.opening_hours').search(cr, uid, [('name', '=', str(dow))], context=context)
		if not oh_ids:
			is_open = False

		exceptions_ids = self.pool.get('membership_lite.oh_exceptions').search(cr, uid, [('date', '=', date_str)], context=context)
		if not exceptions_ids:
			return is_open
		exceptions = self.pool.get('membership_lite.oh_exceptions').browse(cr, uid, exceptions_ids, context=context)
		for e in exceptions:
			if e.closed:
				is_open = False
			else:
				is_open = True

		return is_open


	def get_resource_for_date( self, cr, uid, vals, context=False ):
		_logger = logging.getLogger(__name__)
		if not vals['date']:
			return {}
		date_str = vals['date']
		date = datetime.strptime(date_str, '%Y-%m-%d')
		dow = date.weekday()

		resource_ids = self.search( cr, uid, [('booking_ok', '=', True)], context=context )
		if not resource_ids:
			return {}

		res = []
		oh_ids = self.pool.get('membership_lite.opening_hours').search(cr, uid, [('name', '=', str(dow))], context=context)
		if oh_ids:
			ohs = self.pool.get('membership_lite.opening_hours').browse(cr, uid, oh_ids, context=context)
			for oh in ohs:
				if oh.xtype == '0':
					res = resource_ids
					break
				if oh.xtype == '1':
					if oh.resource_id.id not in res:
						res.append( oh.resource_id.id )

		exceptions_ids = self.pool.get('membership_lite.oh_exceptions').search(cr, uid, [('date', '=', date_str)], context=context)
		if exceptions_ids:
			exceptions = self.pool.get('membership_lite.oh_exceptions').browse(cr, uid, exceptions_ids, context=context)
			for e in exceptions:
				if e.closed and e.xtype == '0':
					res = []
				if e.closed and e.xtype == '1':
					if e.resource_id.id in res:
						res.remove( e.resource_id.id )
				if not e.closed and e.xtype == '0':
					res = resource_ids
				if not e.closed and e.xtype == '1':
					if e.resource_id.id not in res:
						res.append( e.resource_id.id )

		ret = []
		for r in self.browse(cr, uid, res, context=context ):
			ret.append({'id': r.id, 'name': r.name})

		return ret

	def get_name( self, cr, uid, vals, context=None ):
		if not vals['resource']:
			return {'error': 'Resource not provided'}
		resource = self.browse(cr, uid, int(vals['resource']), context=None)
		if not resource:
			return {'name': ''}
		return {'name': resource[0].name}

	def get_hours( self, cr, uid, vals, context=None ):
		_logger = logging.getLogger(__name__)
		if not vals['date']:
			return {'error': 'Date not provided'}
		date_str = vals['date']
		date = datetime.strptime(date_str, '%Y-%m-%d')
		dow = date.weekday()

		if not vals['resource']:
			return {'error': 'Resource not provided'}
		resource_id = int(vals['resource'])

		resource = self.browse(cr, uid, resource_id, context=None)
		if not resource:
			return {'error': 'Resource not found'}

		if not vals['user']:
			return {'error': 'User not provided'}
		user = self.pool.get('res.partner').browse(cr, uid, vals['user'], context=None)
		if not user:
			return {'error': 'User not found'}

		user_status = user.ml_membership_status
		price_message = ''
		price = 0
		if user_status == 'free':
			price_message = 'Price: Free'
		elif user_status == 'paid':
			price_message = 'Price: Included in membership'
		else:
			price_for_unit = resource.price_class.price * 0.5 / resource.price_class.length
			price = price_for_unit
			price_message = 'Price: ' + '{0:.2f}'.format(price_for_unit) + "€"

		wh = []
		oh_ids = self.pool.get('membership_lite.opening_hours').search(cr, uid, [('name', '=', str(dow))], context=context)
		if oh_ids:
			ohs = self.pool.get('membership_lite.opening_hours').browse(cr, uid, oh_ids, context=context)
			resource_bound = False
			for oh in ohs:
				if oh.xtype == '0' and not resource_bound:
					wh.append({'from': oh.hour_from, 'to': oh.hour_to})
				if oh.xtype == '1' and oh.resource_id.id == resource_id:
					if not resource_bound:
						wh = []
						resource_bound = True
					wh.append({'from': oh.hour_from, 'to': oh.hour_to})


		exceptions_ids = self.pool.get('membership_lite.oh_exceptions').search(cr, uid, [('date', '=', date_str)], context=context)
		if exceptions_ids:
			exceptions = self.pool.get('membership_lite.oh_exceptions').browse(cr, uid, exceptions_ids, context=context)
			resource_bound = False
			for e in exceptions:
				if e.closed and e.xtype == '0' and not resource_bound:
					wh = []
				if e.closed and e.xtype == '1' and e.resource_id.id == resource_id:
					if not resource_bound:
						resource_bound = True
					wh = []
				if not e.closed and e.xtype == '0' and not resource_bound:
					wh = []
					wh.append({'from': e.hour_from, 'to': e.hour_to})
				if not e.closed and e.xtype == '1' and e.resource_id.id == resource_id:
					if not resource_bound:
						resource_bound = True
						wh = []
					wh.append({'from': e.hour_from, 'to': e.hour_to})

		res = {}
		if not wh:
			return res

		start = 0
		end = 0
		for hour in wh:
			if start == 0 or start > hour['from']:
				start = hour['from']
			if end == 0 or end < hour['to']:
				end = hour['to']
		res['day_start'] = start
		res['day_end'] = end
		res['hours'] = wh
		res['price_message'] = price_message
		res['price'] = price

		booked = []
		booking_ids = self.pool.get('membership_lite.booking').search(cr, uid, [('resource_id', '=', resource_id), ('day', '=', date_str)], context=context)
		if not booking_ids:
			res['bookings'] = booked
			return res
		bookings = self.pool.get('membership_lite.booking').browse(cr, uid, booking_ids, context=context)

		for booking in bookings:
			booked.append({'from': booking.hour_from, 'to': booking.hour_to})
		res['bookings'] = booked
		_logger.info(res['bookings']);
		return res

	name = fields.Char( 'Name', required="1" )
	desc = fields.Text( 'Description' )
	price_class = fields.Many2one( 'membership_lite.price_class', string="Price class" )
	xtype = fields.Selection([('exclusive', 'Exclusive'), ('shared', 'Shared')], string="Booking type", default="exclusive", required="1")
	max_users = fields.Integer( 'Maximal number of users' )
	booking_ok = fields.Boolean( 'Available for booking' )

class membership_price_class(models.Model):
	_name= "membership_lite.price_class"

	name = fields.Char( 'Name', required="1" )
	desc = fields.Text( 'Description' )
	length = fields.Float( string='Duration', default=1 )
	price = fields.Float( string='Price' )

class membership_opening_hours(models.Model):
	_name = "membership_lite.opening_hours"

	name = fields.Selection([('0','Monday'),('1','Tuesday'),('2','Wednesday'),('3','Thursday'),('4','Friday'),('5','Saturday'),('6','Sunday')], string="Day of week", required="1")
	hour_from = fields.Float(string="Hour from", required="1")
	hour_to = fields.Float(string="Hour to", required="1")
	xtype = fields.Selection([('0', 'All'), ('1', 'For resource')], string='Applies to', default='0', required="1")
	resource_id = fields.Many2one('membership_lite.resource', string="Resource")

class membership_oh_exceptions(models.Model):
	_name = "membership_lite.oh_exceptions"

	name = fields.Char( 'Reason' )
	date = fields.Date( 'Date' )
	closed = fields.Boolean( 'Closed' )
	hour_from = fields.Float( 'From' )
	hour_to = fields.Float( 'To' )
	xtype = fields.Selection([('0', 'All'), ('1', 'For resource')], string='Applies to', default='0', required="1")
	resource_id = fields.Many2one('membership_lite.resource', string="Resource")

class membership_booking(models.Model):
	_name = "membership_lite.booking"

	def make_booking( self, cr, uid, vals, context=None ):
		_logger = logging.getLogger(__name__)
		date = vals['date'] if 'date' in vals else None
		resource = vals['resource'] if 'resource' in vals else None
		t_from = vals['from'] if 'from' in vals else None
		t_to = vals['to'] if 'to' in vals else None
		user_id = vals['user'] if 'user' in vals else None

		if not date or not resource or not t_from or not t_to or not user_id:
			return {'error': 'Incomplete date'}

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

		hours = self.pool.get('membership_lite.resource').get_hours(cr, uid, {'user': user.id, 'date': date, 'resource': resource_id}, context=None)
		if not hours:
			return {'error': 'Failure to retrieve hours!'}
		oh = hours['hours']
		booking = hours['bookings']
		available = False
		for h in oh:
			if t_from >= h['from'] and t_to <= h['to']:
				available = True
		if not available:
			return {'error': 'This time is not available'}

		for b in booking:
			if ( t_from >= b['from'] and t_from < b['to'] ) or ( t_to <= b['to'] and t_to > b['to'] ):
				return {'error': 'This time is not available'}

		duration = t_to - t_from
		halves = duration / 0.5
		transaction_amount = None
		#check member for Payment
		member_status = user.ml_membership_status
		_logger.info("MEMBER STATUS: %s" % member_status)
		if member_status not in ['free', 'paid']:
			credit_status = user.credit_status
			price = resource.price_class.price
			length = resource.price_class.length
			price_per_half = price * 0.5 / length
			price_for_session = price_per_half * halves
			_logger.info("PRICE FOR THIS: %s" % price_for_session)
			if credit_status - price_for_session < 0:
				return {'error': 'Not enough credit for this'}
			#Remove credit from member_id
			purchase_vals = {
				'member': user.id,
				'ml_amount': price_for_session,
				'ml_note': 'Purchase of %sh time for %s' % (length, resource.name),
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
			'note': '' #IMPLEMENT
		}
		success = self.create(cr, uid, new_vals, context=None)
		if not success:
			if transaction_amount:
				rolled_back = self.pool.get('membership_lite.credit_line').unlink( cr, uid, rc_line, context=None)
				if not rolled_back:
					self.unlink(cr, uid, success, context=None)
			return {'error': 'Creating booking did not succeed'}
		new_booking = self.browse( cr, uid, success, context=None)

		return {
			'user': new_booking.member_id.name,
			'date': new_booking.day,
			'from': new_booking.hour_from,
			'to': new_booking.hour_to,
			'resource': new_booking.resource_id.name,
			'note': new_booking.note
		}

	member_id = fields.Many2one( 'res.partner', string="Member", required="1" )
	day = fields.Date( 'Date' )
	hour_from = fields.Float( 'From' )
	hour_to = fields.Float( 'To' )
	resource_id = fields.Many2one('membership_lite.resource', string='Resource', required="1")
	note = fields.Text( 'Note' )
