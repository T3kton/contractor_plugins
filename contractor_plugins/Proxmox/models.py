from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, Complex, Structure, FOUNDATION_SUBCLASS_LIST, COMPLEX_SUBCLASS_LIST
from contractor.Foreman.lib import RUNNER_MODULE_LIST
from contractor.BluePrint.models import FoundationBluePrint
from contractor.lib.config import getConfig, mergeValues

from contractor_plugins.Proxmox.module import set_power, power_state, wait_for_poweroff, destroy, get_interface_map, set_interface_macs

cinp = CInP( 'Proxmox', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'proxmoxfoundation' )
COMPLEX_SUBCLASS_LIST.append( 'proxmoxcomplex' )
RUNNER_MODULE_LIST.append( 'contractor_plugins.Proxmox.module' )


@cinp.model( property_list=( 'state', 'type' ) )
class ProxmoxComplex( Complex ):
  proxmox_host = models.ForeignKey( Structure, on_delete=models.PROTECT, help_text='set to Proxmox host' )  # no need for unique, the same proxmox_host can be used for multiple clusters
  proxmox_username = models.CharField( max_length=50 )
  proxmox_password = models.CharField( max_length=50 )

  @property
  def subclass( self ):
    return self

  @property
  def state( self ):
    if self.proxmox_host.state != 'built':
      return 'planned'

    return super().state

  @property
  def type( self ):
    return 'Proxmox'

  @property
  def connection_parameters( self ):
    if self.proxmox_password == '_VAULT_':
      creds = self.proxmox_username

    else:
      creds = {
                'username': self.proxmox_username,
                'password': self.proxmox_password
              }

    return {
              'host': self.proxmox_host.primary_address.ip_address,
              'credentials': creds
            }

  def newFoundation( self, hostname, site ):
    foundation = ProxmoxFoundation( site=site, blueprint=FoundationBluePrint.objects.get( pk='proxmox-vm-base' ), locator=hostname )
    foundation.proxmox_complex = self
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

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'ProxmoxComplex {0}'.format( self.pk )


def _vmSpec( foundation ):
  result = {}

  if foundation.structure is None:
    raise ValueError( 'No Structure Attached' )

  structure_config = getConfig( foundation.structure )
  structure_config = mergeValues( structure_config )

  result[ 'cpu_count' ] = structure_config.get( 'cpu_count', 1 )
  result[ 'memory_size' ] = structure_config.get( 'memory_size', 1024 )  # in MiB
  result[ 'disk_size' ] = structure_config.get( 'disk_size', 10 )  # in GiB

  return result


@cinp.model( property_list=( 'state', 'type', 'class_list' ), read_only_list=( 'proxmox_id', ) )
class ProxmoxFoundation( Foundation ):
  proxmox_complex = models.ForeignKey( ProxmoxComplex, on_delete=models.PROTECT )
  proxmox_id = models.IntegerField( blank=True, null=True )  # not going to do unique, there could be lots of proxmox clusters

  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( ProxmoxFoundation, ProxmoxFoundation ).getTscriptValues( write_mode )

    result[ 'proxmox_complex' ] = ( lambda foundation: foundation.proxmox_complex, None )
    result[ 'proxmox_id' ] = ( lambda foundation: foundation.proxmox_id, None )
    result[ 'proxmox_vmspec'] = ( lambda foundation: _vmSpec( foundation ), None )

    if write_mode is True:
      result[ 'proxmox_id' ] = ( result[ 'proxmox_id' ][0], lambda foundation, val: setattr( foundation, 'proxmox_id', val ) )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( ProxmoxFoundation, ProxmoxFoundation ).getTscriptFunctions()
    result[ 'power_on' ] = lambda foundation: ( 'proxmox', set_power( foundation, 'on' ) )
    result[ 'power_off' ] = lambda foundation: ( 'proxmox', set_power( foundation, 'off' ) )
    result[ 'power_state' ] = lambda foundation: ( 'proxmox', power_state( foundation ) )
    result[ 'wait_for_poweroff' ] = lambda foundation: ( 'proxmox', wait_for_poweroff( foundation ) )
    result[ 'destroy' ] = lambda foundation: ( 'proxmox', destroy( foundation ) )
    result[ 'get_interface_map' ] = lambda foundation: ( 'proxmox', get_interface_map( foundation ) )
    result[ 'set_interface_macs' ] = lambda foundation: set_interface_macs( foundation )

    return result

  def configAttributes( self ):
    result = super().configAttributes()
    result.update( { '_proxmox_id': self.proxmox_id } )
    result.update( { '_proxmox_complex': self.proxmox_complex.name } )

    return result

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'Proxmox'

  @property
  def class_list( self ):
    return [ 'VM', 'Proxmox' ]

  @property
  def complex( self ):
    return self.proxmox_complex

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return ProxmoxFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if self.pk is not None:
      current = ProxmoxFoundation.objects.get( pk=self.pk )
      if ( self.proxmox_id is not None or current.proxmox_id is not None ) and current.proxmox_complex != self.proxmox_complex:
        errors[ 'proxmox_complex' ] = 'can not move complexes without first destroying'

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'ProxmoxFoundation {0}'.format( self.pk )
