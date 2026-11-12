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

from contractor_plugins.LibVirt.module import set_power, power_state, wait_for_poweroff, destroy, get_interface_map, set_interface_macs

cinp = CInP( 'LibVirt', '0.1', __doc__ )

FOUNDATION_SUBCLASS_LIST.append( 'libvirtfoundation' )
COMPLEX_SUBCLASS_LIST.append( 'libvirtcomplex' )
RUNNER_MODULE_LIST.append( 'contractor_plugins.LibVirt.module' )


@cinp.model( property_list=( 'state', 'type' ) )
class LibVirtComplex( Complex ):
  """
  Complex for LibVirt.  Only one member is allowed.  The ip address
  for managing the LibVirt instance comes from the member's primary ip.
  """

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'LibVirt'

  @property
  def connection_parameters( self ):
    return { 'host': self.members.get().primary_address.ip_address }

  def newFoundation( self, hostname, site ):
    foundation = LibVirtFoundation( site=site, blueprint=FoundationBluePrint.objects.get( pk='libvirt-vm-base' ), locator=hostname )
    foundation.libvirt_complex = self
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
      errors[ 'structure' ] = 'LibVirt Complex support only one structure'

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'LibVirtComplex {0}'.format( self.pk )


def _vmSpec( foundation ):
  result = {}

  if foundation.structure is None:
    raise ValueError( 'No Structure Attached' )

  structure_config = getConfig( foundation.structure )
  structure_config = mergeValues( structure_config )

  result[ 'cpu_count' ] = structure_config.get( 'cpu_count', 1 )
  result[ 'memory_size' ] = structure_config.get( 'memory_size', 1024 )  # in MiB
  result[ 'disk_size' ] = structure_config.get( 'disk_size', 10 )  # in GiB
  result[ 'console_type' ] = foundation.libvirt_console_type

  return result


@cinp.model( property_list=( 'state', 'type', 'class_list' ), read_only_list=( 'libvirt_uuid', ) )
class LibVirtFoundation( Foundation ):
  """
  Foundation for use with LibVirtComplex.  Foundation instances are tracked
  by the LibVirt UUID.
  """
  CONSOLE_TYPE_CHOICES = ( 'spice', 'serial' )
  libvirt_complex = models.ForeignKey( LibVirtComplex, on_delete=models.PROTECT )
  libvirt_uuid = models.CharField( max_length=36, blank=True, null=True )  # not going to do unique, there could be lots of libvvirt hosts
  libvirt_console_type = models.CharField( max_length=6, choices=[ ( i, i ) for i in CONSOLE_TYPE_CHOICES ], default='serial' )

  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( LibVirtFoundation, LibVirtFoundation ).getTscriptValues( write_mode )

    result[ 'libvirt_complex' ] = ( lambda foundation: foundation.libvirt_complex, None )
    result[ 'libvirt_uuid' ] = ( lambda foundation: foundation.libvirt_uuid, None )
    result[ 'libvirt_vmspec'] = ( lambda foundation: _vmSpec( foundation ), None )

    if write_mode is True:
      result[ 'libvirt_uuid' ] = ( result[ 'libvirt_uuid' ][0], lambda foundation, val: setattr( foundation, 'libvirt_uuid', val ) )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( LibVirtFoundation, LibVirtFoundation ).getTscriptFunctions()
    result[ 'power_on' ] = lambda foundation: ( 'libvirt', set_power( foundation, 'on' ) )
    result[ 'power_off' ] = lambda foundation: ( 'libvirt', set_power( foundation, 'off' ) )
    result[ 'power_state' ] = lambda foundation: ( 'libvirt', power_state( foundation ) )
    result[ 'wait_for_poweroff' ] = lambda foundation: ( 'libvirt', wait_for_poweroff( foundation ) )
    result[ 'destroy' ] = lambda foundation: ( 'libvirt', destroy( foundation ) )
    result[ 'get_interface_map' ] = lambda foundation: ( 'libvirt', get_interface_map( foundation ) )
    result[ 'set_interface_macs' ] = lambda foundation: set_interface_macs( foundation )

    return result

  def configAttributes( self ):
    result = super().configAttributes()
    result.update( { '_libvirt_uuid': self.libvirt_uuid } )
    result.update( { '_libvirt_complex': self.libvirt_complex.name } )

    return result

  @property
  def console( self ):
    if self.libvirt_console_type == 'spice':
      return 'console'

    return 'ttyS0'  # <console type='pty'/> is the guest's first serial port

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'LibVirt'

  @property
  def class_list( self ):
    return [ 'VM', 'LibVirt' ]

  @property
  def complex( self ):
    return self.libvirt_complex

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return LibVirtFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if self.pk is not None:
      current = LibVirtFoundation.objects.get( pk=self.pk )
      if ( self.libvirt_uuid is not None or current.libvirt_uuid is not None ) and current.libvirt_complex != self.libvirt_complex:
        errors[ 'libvirt_complex' ] = 'can not move complexes without first destroying'

    if self.site.pk != self.libvirt_complex.site.pk:
      errors[ 'site' ] = 'Site must match the libvirt_complex\'s site'

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'VLibVirtFoundation {0}'.format( self.pk )
