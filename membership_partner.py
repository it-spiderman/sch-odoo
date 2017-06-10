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
	ml_rfid = fields.Char( 'RFID' )
