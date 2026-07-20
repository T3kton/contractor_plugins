import re
from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, Complex, Structure, FOUNDATION_SUBCLASS_LIST, COMPLEX_SUBCLASS_LIST
from contractor.Foreman.lib import RUNNER_MODULE_LIST
from contractor.BluePrint.models import FoundationBluePrint
from contractor.lib.config import getConfig, mergeValues

from contractor_plugins.VCenter.module import set_power, power_state, wait_for_poweroff, destroy, get_interface_map, set_interface_macs, execute, mark_as_template, export

cinp = CInP( 'VCenter', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'vcenterfoundation' )
COMPLEX_SUBCLASS_LIST.append( 'vcentercomplex' )
RUNNER_MODULE_LIST.append( 'contractor_plugins.VCenter.module' )

datacenter_name_regex = re.compile( r'^[a-zA-Z0-9][a-zA-Z0-9_\-]*$' )
cluster_name_regex = re.compile( r'^[a-zA-Z0-9][a-zA-Z0-9_\-\.]*$' )


@cinp.model( property_list=( 'state', 'type' ) )
class VCenterComplex( Complex ):
  vcenter_host = models.ForeignKey( Structure, on_delete=models.PROTECT, help_text='set to VCenter or the ESX host, if ESX host, leave members empty' )  # no need for unique, the same vcenter_host can be used for multiple clusters
  vcenter_username = models.CharField( max_length=50 )
  vcenter_password = models.CharField( max_length=50 )
  vcenter_datacenter = models.CharField( max_length=50, help_text='set to "ha-datacenter" for ESX hosts' )
  vcenter_cluster = models.CharField( max_length=50, help_text='set to the hostname (ie: "localhost.") for ESX hosts' )

  @property
  def subclass( self ):
    return self

  @property
  def state( self ):
    if self.vcenter_host.state != 'built':
      return 'planned'

    return super().state

  @property
  def type( self ):
    return 'VCenter'

  @property
  def connection_parameters( self ):
    if self.vcenter_password == '_VAULT_':
      creds = self.vcenter_username

    else:
      creds = {
                'username': self.vcenter_username,
                'password': self.vcenter_password
              }

    return {
              'host': self.vcenter_host.primary_address.ip_address,
              'credentials': creds
            }

  def newFoundation( self, hostname, site ):
    foundation = VCenterFoundation( site=site, blueprint=FoundationBluePrint.objects.get( pk='vcenter-vm-base' ), locator=hostname )
    foundation.vcenter_complex = self
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

    if self.vcenter_datacenter and not datacenter_name_regex.match( self.vcenter_datacenter ):
      errors[ 'vcenter_datacenter' ] = '"{0}" is invalid'.format( self.vcenter_datacenter )

    if self.vcenter_cluster and not cluster_name_regex.match( self.vcenter_cluster ):
      errors[ 'vcenter_cluster' ] = '"{0}" is invalid'.format( self.vcenter_cluster )

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'VCenterComplex {0}'.format( self.pk )


def _vmSpec( foundation ):
  result = {}

  if foundation.structure is None:
    raise ValueError( 'No Structure Attached' )

  structure_config = getConfig( foundation.structure )
  structure_config = mergeValues( structure_config )

  result[ 'cpu_count' ] = structure_config.get( 'cpu_count', 1 )
  result[ 'memory_size' ] = structure_config.get( 'memory_size', 1024 )  # in MiB
  result[ 'disk_size' ] = structure_config.get( 'disk_size', 10 )  # in GiB

  if 'ova' in structure_config:
    result[ 'ova' ] = structure_config[ 'ova' ]

    for key in ( 'vcenter_property_map', 'vcenter_deployment_option', 'vcenter_ip_protocol' ):
      try:
        result[ key ] = structure_config[ key ]
      except KeyError:
        pass

  if 'template' in structure_config:
    result[ 'template' ] = structure_config[ 'template' ]

    for key in ( 'vcenter_hostname', 'vcenter_domain', 'vcenter_dnsserver_list', 'vcenter_dnssuffix_list', 'vcenter_property_map' ):
      try:
        result[ key ] = structure_config[ key ]
      except KeyError:
        pass

  else:
    result[ 'vcenter_guest_id' ] = structure_config.get( 'vcenter_guest_id', 'otherGuest' )

    for key in ( 'vcenter_virtual_exec_usage', 'vcenter_virtual_mmu_usage', 'vcenter_virtual_vhv', 'vcenter_network_interface_class', 'vcenter_property_map' ):
      try:
        result[ key ] = structure_config[ key ]
      except KeyError:
        pass

  return result


@cinp.model( property_list=( 'state', 'type', 'class_list' ), read_only_list=( 'vcenter_uuid', ) )
class VCenterFoundation( Foundation ):
  vcenter_complex = models.ForeignKey( VCenterComplex, on_delete=models.PROTECT )
  vcenter_uuid = models.CharField( max_length=36, blank=True, null=True )  # not going to do unique, there could be lots of vcenter clusters

  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( VCenterFoundation, VCenterFoundation ).getTscriptValues( write_mode )

    result[ 'vcenter_complex' ] = ( lambda foundation: foundation.vcenter_complex, None )
    result[ 'vcenter_uuid' ] = ( lambda foundation: foundation.vcenter_uuid, None )
    result[ 'vcenter_vmspec'] = ( lambda foundation: _vmSpec( foundation ), None )

    if write_mode is True:
      result[ 'vcenter_uuid' ] = ( result[ 'vcenter_uuid' ][0], lambda foundation, val: setattr( foundation, 'vcenter_uuid', val ) )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( VCenterFoundation, VCenterFoundation ).getTscriptFunctions()
    result[ 'power_on' ] = lambda foundation: ( 'vcenter', set_power( foundation, 'on' ) )
    result[ 'power_off' ] = lambda foundation: ( 'vcenter', set_power( foundation, 'off' ) )
    result[ 'power_state' ] = lambda foundation: ( 'vcenter', power_state( foundation ) )
    result[ 'wait_for_poweroff' ] = lambda foundation: ( 'vcenter', wait_for_poweroff( foundation ) )
    result[ 'destroy' ] = lambda foundation: ( 'vcenter', destroy( foundation ) )
    result[ 'get_interface_map' ] = lambda foundation: ( 'vcenter', get_interface_map( foundation ) )
    result[ 'set_interface_macs' ] = lambda foundation: set_interface_macs( foundation )
    result[ 'execute' ] = lambda foundation: ( 'vcenter', execute( foundation ) )
    result[ 'mark_as_template' ] = lambda foundation: ( 'vcenter', mark_as_template( foundation ) )
    result[ 'export' ] = lambda foundation: ( 'vcenter', export( foundation ) )

    return result

  def configAttributes( self ):
    result = super().configAttributes()
    result.update( { '_vcenter_uuid': self.vcenter_uuid } )
    result.update( { '_vcenter_complex': self.vcenter_complex.name } )
    result.update( { '_vcenter_datacenter': self.vcenter_complex.vcenter_datacenter } )
    result.update( { '_vcenter_cluster': self.vcenter_complex.vcenter_cluster } )

    return result

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'VCenter'

  @property
  def class_list( self ):
    return [ 'VM', 'VCenter' ]

  @property
  def complex( self ):
    return self.vcenter_complex

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return VCenterFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if self.pk is not None:
      current = VCenterFoundation.objects.get( pk=self.pk )
      if ( self.vcenter_uuid is not None or current.vcenter_uuid is not None ) and current.vcenter_complex != self.vcenter_complex:
        errors[ 'vcenter_complex' ] = 'can not move complexes without first destroying'

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'VCenterFoundation {0}'.format( self.pk )
