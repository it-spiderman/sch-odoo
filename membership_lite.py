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
	resource_ids = fields.Many2many( comodel_name='membership_lite.resource',
                        relation='resource_profile_rel',
                        column1='profile_id',
                        column2='resource_id', string="Included resources" )

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

	def add_credit(self, cr, uid, vals, context=None):
		_logger = logging.getLogger(__name__)
		user_id = vals['user']
		user = self.pool.get('res.partner').browse(cr, uid, user_id, context=None)
		if not user:
			return {'error': 'No user provided'}
		paypal = vals['paypal']
		if not paypal:
			return {'error': 'No paypal info provided'}

		trans_id = paypal['id']
		state = paypal['state']
		if state != 'approved':
			return {}
		trans_amount = paypal['transactions'][0]['amount']
		trans_curr = trans_amount['currency']
		if trans_curr != 'EUR':
			return {}
		trans_total = float(trans_amount['total'])

		xvals = {
			'member': user.id,
			'date': datetime.today(),
			'ml_amount': trans_total,
			'ml_payment_method': 'paypal',
			'ml_note': "Payment id: %s" % trans_id,
			'ml_direction': 'in',
			'ml_transfer_id': trans_id
		}

		tm_line = self.create(cr, uid, xvals, context=None)
		if not tm_line:
			return {'error': 'Line not created'}
		return {'success': 'true'}

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

	def is_included( self, cr, uid, vals, context=None ):
		user_id = vals['user']
		resource_id = vals['resource']

		user = self.browse(cr, uid, user_id, context=None)
		if not user:
			return False

		for line in user.ml_membership_lines:
			today = datetime.today().date();
			start = datetime.strptime(line.ml_start, '%Y-%m-%d').date()
			end = datetime.strptime(line.ml_end, '%Y-%m-%d').date()
			if start <= today and end >= today:
				for resource in line.ml_profile.resource_ids:
					if resource.booking_ok and resource.id == resource_id:
						return True

		return False

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
			'address': "%s %s, %s %s (%s)" % (user.street or '', user.street2 or '', user.zip or '', user.city or '', user.country_id.name if user.country_id else ''),
			'phone': "Tel: %s</br> Mobile: %s</br> Fax: %s</br>" % (user.phone or '-', user.mobile or '-', user.fax or '-'),
			'email': user.email,
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
		booking_lines = []
		m_lines = user.ml_membership_lines
		c_lines = user.ml_credit_lines
		booking_ids = self.pool.get('membership_lite.booking').search(cr, uid, [('member_id', '=', user.id)], context=None)
		if booking_ids:
			bookings = self.pool.get('membership_lite.booking').browse(cr, uid, booking_ids, context=None)
			for booking in bookings:
				booking_lines.append({
					'date': booking.day,
					'from': booking.hour_from,
					'to': booking.hour_to,
					'resource': booking.resource_id.name,
					'note': booking.note
				})
		for line in m_lines:
			is_current = False
			today = datetime.today().date();
			start = datetime.strptime(line.ml_start, '%Y-%m-%d').date()
			end = datetime.strptime(line.ml_end, '%Y-%m-%d').date()
			if start <= today and end >= today:
				is_current = True
			includes = []
			for i in line.ml_profile.resource_ids:
				includes.append(i.name)
			rm_lines.append({
				'date': line.date,
				'profile': line.ml_profile.name,
				'price': line.ml_price,
				'start': line.ml_start,
				'end': line.ml_end,
				'is_current': is_current,
				'includes': includes
			})
		for line in c_lines:
			rc_lines.append({
				'date': line.date,
				'desc': line.ml_note,
				'amount': line.ml_amount if line.ml_direction == 'in' else line.ml_amount * -1,
				'method': line.ml_payment_method
			})

		res['m_lines'] = rm_lines
		res['c_lines'] = rc_lines
		res['booking_lines'] = booking_lines
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

		if not vals['user']:
			return {}
		user = self.pool.get('res.partner').browse(cr, uid, vals['user'], context=None)
		if not user:
			return {}

		if user.ml_membership_status not in ['paid', 'free']:
			return {}

		resource_ids = []
		for line in user.ml_membership_lines:
			today = datetime.today().date();
			start = datetime.strptime(line.ml_start, '%Y-%m-%d').date()
			end = datetime.strptime(line.ml_end, '%Y-%m-%d').date()
			if start <= today and end >= today:
				for resource in line.ml_profile.resource_ids:
					if resource.booking_ok:
						resource_ids.append( resource.id )
		#resource_ids = self.search( cr, uid, [('booking_ok', '=', True)], context=context )
		if not resource_ids:
			return {}
		_logger.info("INITIAL RESOUCES: %s" % resource_ids )
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
		if user_status not in ['free', 'paid']:
			return {'error': 'User has no packages active'}

		#price_message = ''
		#price = 0
		#if user_status == 'free':
		#	price_message = 'Price: Free'
		#elif user_status == 'paid':
		#	price_message = 'Price: Included in membership'
		#else:
		#	price_for_unit = resource.price_class.price * 0.5 / resource.price_class.length
		#	price = price_for_unit
		#	price_message = 'Price: ' + '{0:.2f}'.format(price_for_unit) + "€"

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

		#res['hours'] = wh
		#res['price_message'] = price_message
		#res['price'] = price

		booked = []
		booking_ids = self.pool.get('membership_lite.booking').search(cr, uid, [('resource_id', '=', resource_id), ('day', '=', date_str)], context=context)
		if booking_ids:
			bookings = self.pool.get('membership_lite.booking').browse(cr, uid, booking_ids, context=context)

			for booking in bookings:
				booked.append({'from': booking.hour_from, 'to': booking.hour_to})

		day_hours = []
		control = start
		while control <= end:
			tstart = control
			control += 1
			tend = control
			is_open = False
			for period in wh:
				if tstart >= period['from'] and tend <= period['to']:
					is_open = True
					break
			if not is_open:
				day_hours.append({
					'available': False,
					'reason': 'closed',
					'from': tstart,
					'to': tend,
					'price': 0,
					'price_message': ''
				})
				continue
			is_booked = False
			for period in booked:
				if tstart >= period['from'] and tend <= period['to']:
					is_booked = True
					break
			if is_booked:
				day_hours.append({
					'available': False,
					'reason': 'booked',
					'from': tstart,
					'to': tend,
					'price': 0,
					'price_message': ''
				})
				continue

			price = self.pool.get('membership_lite.price_rule').get_price( cr, uid, {'start': tstart, 'end': tend, 'dow': dow, 'date': date}, context=None)
			day_hours.append({
				'available': True if price else False,
				'reason': '' if price else 'Error getting price',
				'from': tstart,
				'to': tend,
				'price': price if price else 0,
				'price_message': 'Price: ' + '{0:.2f}'.format(price) + "€" if price else ''
			})

		res['hours'] = day_hours
		return res

	name = fields.Char( 'Name', required="1" )
	desc = fields.Text( 'Description' )
	xtype = fields.Selection([('exclusive', 'Exclusive'), ('shared', 'Shared')], string="Booking type", default="exclusive", required="1")
	max_users = fields.Integer( 'Maximal number of users' )
	booking_ok = fields.Boolean( 'Available for booking' )

class membership_price_rule(models.Model):
	_name= "membership_lite.price_rule"

	def get_price( self, cr, uid, vals, context=None ):
		_logger = logging.getLogger(__name__)
		start = vals['start']
		end = vals['end']
		dow = vals['dow']
		date = vals['date']

		times = []
		if end - start > 1:
			cnt = start
			while cnt <= end:
				xstart = cnt
				cnt += 1
				xend = cnt
				times.append({'start': xstart, 'end': xend})
		else:
			times.append({'start': start, 'end': end})

		rule_ids = self.search(cr, uid, [('active', '=', True)], context=None)
		if not rule_ids:
			return False
		rules = self.browse(cr, uid, rule_ids, context=None)
		total_price = 0
		for time in times:
			applying_rules = []
			date_bound = False
			for rule in rules:
				if rule.date == date:
					if not date_bound:
						date_bound = True
						applying_rules = []
					applying_rules.append(rule)
					continue
				if rule.name == str(dow) and not date_bound:
					applying_rules.append(rule)
					continue
			price = False
			for rule in applying_rules:
				if not rule.hour_from and not rule.hour_to:
					price = rule.price
				if rule.hour_from and not rule.hour_to and rule.hour_from <= time['start']:
					price = rule.price
				if not rule.hour_from and rule.hour_to and rule.hour_to >= time['end']:
					price = rule.price
				if rule.hour_from and rule.hour_to and rule.hour_from <= time['start'] and rule.hour_to >= time['end']:
					price = rule.price

			total_price += price

		return total_price


	name = fields.Selection([('0','Monday'),('1','Tuesday'),('2','Wednesday'),('3','Thursday'),('4','Friday'),('5','Saturday'),('6','Sunday')], string="Day of week", required="1")
	hour_from = fields.Float(string="Hour from")
	hour_to = fields.Float(string="Hour to")
	date = fields.Date(string="Date")
	desc = fields.Text( 'Description' )
	price = fields.Float( string='Price' )
	active = fields.Boolean( 'Active', default=True )

class membership_long_booking(models.Model):
	_name = "membership_lite.long_booking"

	duration = fields.Integer( 'Duration in months' )
	price = fields.Float( 'Price (for 1h)' )
	xtype = fields.Selection([('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly')], default="weekly", required="1", string="Type" )
	min_booking = fields.Integer( string='Mininal booking time (in h)', default=1 )

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
			hours_to_check.append({'start': t_from, 'end': t_end})
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
