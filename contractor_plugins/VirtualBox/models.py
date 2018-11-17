from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from contractor.Building.models import Foundation, Complex, FOUNDATION_SUBCLASS_LIST, COMPLEX_SUBCLASS_LIST
from contractor.Utilities.models import RealNetworkInterface
from contractor.BluePrint.models import FoundationBluePrint
from contractor.Foreman.lib import RUNNER_MODULE_LIST

from contractor_plugins.VirtualBox.module import set_power, power_state, wait_for_poweroff, destroy, set_interface_macs

cinp = CInP( 'VirtualBox', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'virtualboxfoundation' )
COMPLEX_SUBCLASS_LIST.append( 'virtualboxcomplex' )
RUNNER_MODULE_LIST.append( 'contractor_plugins.VirtualBox.module' )


@cinp.model( property_list=( 'state', 'type' ) )
class VirtualBoxComplex( Complex ):
  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'VirtualBox'

  def newFoundation( self, hostname ):
    foundation = VirtualBoxFoundation( site=self.site, blueprint=FoundationBluePrint.objects.get( pk='virtualbox-vm-base' ), locator=hostname )
    foundation.virtualbox_host = self
    foundation.full_clean()
    foundation.save()

    iface = RealNetworkInterface( name='eth0', is_provisioning=True )
    iface.foundation = foundation
    iface.physical_location = 'eth0'
    iface.full_clean()
    iface.save()

    return foundation

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return True

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if self.pk and self.members.count() > 1:
      errors[ 'structure' ] = 'VirtualBox Complex support only one structure'

    if errors:
      raise ValidationError( errors )

  def __str__( self ):
    return 'VirtualBoxComplex {0}'.format( self.pk )


@cinp.model( property_list=( 'state', 'type', 'class_list' ) )
class VirtualBoxFoundation( Foundation ):
  virtualbox_host = models.ForeignKey( VirtualBoxComplex, on_delete=models.PROTECT )
  virtualbox_uuid = models.CharField( max_length=36, blank=True, null=True )  # not going to do unique, there could be lots of virtualbox hosts

  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( VirtualBoxFoundation, VirtualBoxFoundation ).getTscriptValues( write_mode )

    result[ 'virtualbox_host' ] = ( lambda foundation: foundation.virtualbox_host, None )
    result[ 'virtualbox_uuid' ] = ( lambda foundation: foundation.virtualbox_uuid, None )

    if write_mode is True:
      result[ 'virtualbox_uuid' ] = ( result[ 'virtualbox_uuid' ][0], lambda foundation, val: setattr( foundation, 'virtualbox_uuid', val ) )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( VirtualBoxFoundation, VirtualBoxFoundation ).getTscriptFunctions()
    result[ 'power_on' ] = lambda foundation: ( 'virtualbox', set_power( foundation, 'on' ) )
    result[ 'power_off' ] = lambda foundation: ( 'virtualbox', set_power( foundation, 'off' ) )
    result[ 'power_state' ] = lambda foundation: ( 'virtualbox', power_state( foundation ) )
    result[ 'wait_for_poweroff' ] = lambda foundation: ( 'virtualbox', wait_for_poweroff( foundation ) )
    result[ 'destroy' ] = lambda foundation: ( 'virtualbox', destroy( foundation ) )
    result[ 'set_interface_macs' ] = lambda foundation: set_interface_macs( foundation )

    return result

  def configAttributes( self ):
    result = super().configAttributes()
    result.update( { '_virtualbox_uuid': self.virtualbox_uuid } )
    result.update( { '_virtualbox_host': self.virtualbox_host.name } )

    return result

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'VirtualBox'

  @property
  def class_list( self ):
    return [ 'VM', 'VirtualBox' ]

  @property
  def can_auto_locate( self ):
    try:
      return self.virtualbox_host.state == 'built' and self.structure.auto_build
    except AttributeError:
      return False

  @property
  def complex( self ):
    return self.virtualbox_host

  @cinp.list_filter( name='site', paramater_type_list=[ { 'type': 'Model', 'model': 'contractor.Site.models.Site' } ] )
  @staticmethod
  def filter_site( site ):
    return VirtualBoxFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return True

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if self.site.pk != self.virtualbox_host.site.pk:
      errors[ 'site' ] = 'Site must match the virtualbox_host\'s site'

    if errors:
      raise ValidationError( errors )

  def __str__( self ):
    return 'VirtualBoxFoundation {0}'.format( self.pk )