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
			m_lines = member.ml_membership_lines
			if not m_lines:
				member.ml_membership_status = 'none'
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

	def get_profile_info( self, cr, uid, vals, context=None ):
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
		res['c_lines'] = rm_lines

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
					res.append( e.resource_id.id )

		ret = []
		for r in self.browse(cr, uid, res, context=context ):
			ret.append({'id': r.id, 'name': r.name})

		return ret

	def get_work_hours( self, cr, uid, vals, context=None ):
		if not vals['date']:
			return {'error': 'Date not provided'}
		date_str = vals['date']
		date = datetime.strptime(date_str, '%Y-%m-%d')
		dow = date.weekday()

		if not vals['resource']:
			return {'error': 'Resource not provided'}
		resource_id = vals['resource']

		working_hours = []
		oh_ids = self.pool.get('membership_lite.opening_hours').search(cr, uid, [('name', '=', str(dow))], context=context)
		if oh_ids:
			ohs = self.pool.get('membership_lite.opening_hours').browse(cr, uid, oh_ids, context=context)
			wh = {}
			for oh in ohs:
				if oh.xtype == '0':
					break
				if oh.xtype == '1':
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
					res.append( e.resource_id.id )


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

	member_id = fields.Many2one( 'res.partner', string="Member", required="1" )
	day = fields.Date( 'Date' )
	hour_from = fields.Float( 'From' )
	hour_to = fields.Float( 'To' )
	resource_id = fields.Many2one('membership_lite.resource', string='Resource', required="1")
	note = fields.Text( 'Note' )
