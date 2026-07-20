"""
Plugin for VirtualBox.
"""

from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, Complex, FOUNDATION_SUBCLASS_LIST, COMPLEX_SUBCLASS_LIST
from contractor.BluePrint.models import FoundationBluePrint
from contractor.lib.config import getConfig, mergeValues
from contractor.Foreman.lib import RUNNER_MODULE_LIST

from contractor_plugins.VirtualBox.module import set_power, power_state, wait_for_poweroff, destroy, get_interface_map, set_interface_macs

cinp = CInP( 'VirtualBox', '0.1', __doc__ )

FOUNDATION_SUBCLASS_LIST.append( 'virtualboxfoundation' )
COMPLEX_SUBCLASS_LIST.append( 'virtualboxcomplex' )
RUNNER_MODULE_LIST.append( 'contractor_plugins.VirtualBox.module' )


@cinp.model( property_list=( 'state', 'type' ) )
class VirtualBoxComplex( Complex ):
  """
  Complex for VirtualBox.  Only one member is allowed.  The ip address
  for managing the VirtualBox instance comes from the member's primary ip.
  """
  virtualbox_username = models.CharField( max_length=50 )
  virtualbox_password = models.CharField( max_length=50 )

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'VirtualBox'

  @property
  def connection_parameters( self ):
    if self.virtualbox_password == '_VAULT_':
      creds = self.virtualbox_username

    else:
      creds = {
                'username': self.virtualbox_username,
                'password': self.virtualbox_password
              }

    return {
              'host': self.members.get().primary_address.ip_address,
              'credentials': creds
            }

  def newFoundation( self, hostname, site ):
    foundation = VirtualBoxFoundation( site=site, blueprint=FoundationBluePrint.objects.get( pk='virtualbox-vm-base' ), locator=hostname )
    foundation.virtualbox_complex = self
    foundation.full_clean()
    foundation.save()

    return foundation

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if self.pk is not None and self.members.count() > 1:
      errors[ 'structure' ] = 'VirtualBox Complex support only one structure'

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'VirtualBoxComplex {0}'.format( self.pk )


def _vmSpec( foundation ):
  result = {}

  if foundation.structure is None:
    raise ValueError( 'No Structure Attached' )

  structure_config = getConfig( foundation.structure )
  structure_config = mergeValues( structure_config )

  result[ 'cpu_count' ] = structure_config.get( 'cpu_count', 1 )
  result[ 'memory_size' ] = structure_config.get( 'memory_size', 1024 )  # in MiB
  result[ 'disk_size' ] = structure_config.get( 'disk_size', 10 )  # in GiB

  result[ 'virtualbox_guest_type' ] = structure_config.get( 'virtualbox_guest_type', 'Other' )

  for key in ( 'virtualbox_network_adapter_type', ):
    try:
      result[ key ] = structure_config[ key ]
    except KeyError:
      pass

  return result


@cinp.model( property_list=( 'state', 'type', 'class_list' ), read_only_list=( 'virtualbox_uuid', ) )
class VirtualBoxFoundation( Foundation ):
  """
  Foundation for use with VirtualBoxComplex.  Foundation instances are tracked
  by the internal VirtualBox Hardware UUID.
  """
  virtualbox_complex = models.ForeignKey( VirtualBoxComplex, on_delete=models.PROTECT )
  virtualbox_uuid = models.CharField( max_length=36, blank=True, null=True )  # not going to do unique, there could be lots of virtualbox hosts

  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( VirtualBoxFoundation, VirtualBoxFoundation ).getTscriptValues( write_mode )

    result[ 'virtualbox_complex' ] = ( lambda foundation: foundation.virtualbox_complex, None )
    result[ 'virtualbox_uuid' ] = ( lambda foundation: foundation.virtualbox_uuid, None )
    result[ 'virtualbox_vmspec'] = ( lambda foundation: _vmSpec( foundation ), None )

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
    result[ 'get_interface_map' ] = lambda foundation: ( 'virtualbox', get_interface_map( foundation ) )
    result[ 'set_interface_macs' ] = lambda foundation: set_interface_macs( foundation )

    return result

  def configAttributes( self ):
    result = super().configAttributes()
    result.update( { '_virtualbox_uuid': self.virtualbox_uuid } )
    result.update( { '_virtualbox_complex': self.virtualbox_complex.name } )

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
  def complex( self ):
    return self.virtualbox_complex

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return VirtualBoxFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if self.pk is not None:
      current = VirtualBoxFoundation.objects.get( pk=self.pk )
      if ( self.virtualbox_uuid is not None or current.virtualbox_uuid is not None ) and current.virtualbox_complex != self.virtualbox_complex:
        errors[ 'virtualbox_complex' ] = 'can not move complexes without first destroying'

    if self.site.pk != self.virtualbox_complex.site.pk:
      errors[ 'site' ] = 'Site must match the virtualbox_complex\'s site'

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'VirtualBoxFoundation {0}'.format( self.pk )
