from __future__ import unicode_literals
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from .fields import HexIntegerField
from .settings import PUSH_NOTIFICATIONS_SETTINGS as SETTINGS


CLOUD_MESSAGE_TYPES = (
	("GCM", "Google Cloud Message"),
	("FCM", "Firebase Cloud Message"),
)


@python_2_unicode_compatible
class Device(models.Model):
	name = models.CharField(max_length=255, verbose_name=_("Name"), blank=True, null=True)
	active = models.BooleanField(
		verbose_name=_("Is active"), default=True,
		help_text=_("Inactive devices will not be sent notifications")
	)
	user = models.ForeignKey(SETTINGS["USER_MODEL"], blank=True, null=True, on_delete=models.CASCADE)
	date_created = models.DateTimeField(
		verbose_name=_("Creation date"), auto_now_add=True, null=True
	)

	class Meta:
		abstract = True

	def __str__(self):
		return (
			self.name or str(self.device_id or "") or
			"%s for %s" % (self.__class__.__name__, self.user or "unknown user")
		)


class GCMDeviceManager(models.Manager):
	def get_queryset(self):
		return GCMDeviceQuerySet(self.model)


class GCMDeviceQuerySet(models.query.QuerySet):
	def send_message(self, message, **kwargs):
		if self:
			from .gcm import send_bulk_message

			data = kwargs.pop("extra", {})
			if message is not None:
				data["message"] = message

			response = []
			for cloud_type in ("GCM", "FCM"):
				reg_ids = list(
					self.filter(active=True, cloud_message_type=cloud_type).values_list(
						"registration_id", flat=True
					)
				)
				if reg_ids:
					r = send_bulk_message(
						registration_ids=reg_ids, data=data, cloud_type=cloud_type, **kwargs
					)
					response.append(r)

			return response


class GCMDevice(Device):
	# device_id cannot be a reliable primary key as fragmentation between different devices
	# can make it turn out to be null and such:
	# http://android-developers.blogspot.co.uk/2011/03/identifying-app-installations.html
	device_id = HexIntegerField(
		verbose_name=_("Device ID"), blank=True, null=True, db_index=True,
		help_text=_("ANDROID_ID / TelephonyManager.getDeviceId() (always as hex)")
	)
	registration_id = models.TextField(verbose_name=_("Registration ID"))
	cloud_message_type = models.CharField(
		verbose_name=_("Cloud Message Type"), max_length=3,
		choices=CLOUD_MESSAGE_TYPES, default="GCM",
		help_text=_("You should choose GCM or FCM")
	)
	objects = GCMDeviceManager()

	class Meta:
		verbose_name = _("GCM device")

	def send_message(self, message, **kwargs):
		from .gcm import send_message

		data = kwargs.pop("extra", {})
		if message is not None:
			data["message"] = message

		return send_message(
			registration_id=self.registration_id, data=data,
			cloud_type=self.cloud_message_type, **kwargs
		)


class APNSDeviceManager(models.Manager):
	def get_queryset(self):
		return APNSDeviceQuerySet(self.model)


class APNSDeviceQuerySet(models.query.QuerySet):
	def send_message(self, message, **kwargs):
		if self:
			from .apns import apns_send_bulk_message
			reg_ids = list(self.filter(active=True).values_list("registration_id", flat=True))
			if reg_ids:
				return apns_send_bulk_message(registration_ids=reg_ids, alert=message, **kwargs)


class APNSDevice(Device):
	device_id = models.UUIDField(
		verbose_name=_("Device ID"), blank=True, null=True, db_index=True,
		help_text="UDID / UIDevice.identifierForVendor()"
	)
	registration_id = models.CharField(
		verbose_name=_("Registration ID"), max_length=200, unique=True
	)

	objects = APNSDeviceManager()

	class Meta:
		verbose_name = _("APNS device")

	def send_message(self, message, **kwargs):
		from .apns import apns_send_message

		return apns_send_message(registration_id=self.registration_id, alert=message, **kwargs)


class WNSDeviceManager(models.Manager):
	def get_queryset(self):
		return WNSDeviceQuerySet(self.model)


class WNSDeviceQuerySet(models.query.QuerySet):
	def send_message(self, message, **kwargs):
		if self:
			from .wns import wns_send_bulk_message

			reg_ids = list(self.filter(active=True).values_list("registration_id", flat=True))
			return wns_send_bulk_message(uri_list=reg_ids, message=message, **kwargs)


class WNSDevice(Device):
	device_id = models.UUIDField(
		verbose_name=_("Device ID"), blank=True, null=True, db_index=True,
		help_text=_("GUID()")
	)
	registration_id = models.TextField(verbose_name=_("Notification URI"))

	objects = WNSDeviceManager()

	class Meta:
		verbose_name = _("WNS device")

	def send_message(self, message, **kwargs):
		from .wns import wns_send_message

		return wns_send_message(uri=self.registration_id, message=message, **kwargs)


# This is an APNS-only function right now, but maybe GCM will implement it
# in the future.  But the definition of 'expired' may not be the same. Whatevs
def get_expired_tokens(cerfile=None):
	from .apns import apns_fetch_inactive_ids
	return apns_fetch_inactive_ids(cerfile)
