import re
from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, Complex, FOUNDATION_SUBCLASS_LIST, COMPLEX_SUBCLASS_LIST
from contractor.Foreman.lib import RUNNER_MODULE_LIST
from contractor.BluePrint.models import FoundationBluePrint
from contractor.lib.config import getConfig, mergeValues

from contractor_plugins.Azure.module import set_power, power_state, destroy

cinp = CInP( 'Azure', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'azurefoundation' )
COMPLEX_SUBCLASS_LIST.append( 'azurecomplex' )
RUNNER_MODULE_LIST.append( 'contractor_plugins.Azure.module' )

uuid_regex = re.compile( r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' )
resource_group_regex = re.compile( r'^[-\w\._\(\)]+$' )  # from https://docs.microsoft.com/en-us/rest/api/resources/resourcegroups/createorupdate


@cinp.model( property_list=( 'state', 'type' ) )
class AzureComplex( Complex ):
  azure_subscription_id = models.CharField( max_length=36 )
  azure_location = models.CharField( max_length=20 )
  azure_resource_group = models.CharField( max_length=90 )  # case insensitive
  azure_client_id = models.CharField( max_length=36, help_text='also called App Id' )
  azure_password = models.CharField( max_length=36 )
  azure_tenant_id = models.CharField( max_length=36 )

  @property
  def subclass( self ):
    return self

  @property
  def state( self ):
    return 'built'

  @property
  def type( self ):
    return 'Azure'

  @property
  def connection_parameters( self ):
    return {
              'subscription_id': self.azure_subscription_id,
              'client_id': self.azure_client_id,
              'password': self.azure_password,
              'tenant_id': self.azure_tenant_id
            }

  def newFoundation( self, hostname, site ):
    foundation = AzureFoundation( site=site, blueprint=FoundationBluePrint.objects.get( pk='azure-vm-base' ), locator=hostname )
    foundation.azure_complex = self
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

    if self.pk is not None and self.members.count() > 0:
      errors[ 'structure' ] = 'Azure Complex dosent have members'

    self.azure_resource_group = self.azure_resource_group.lower()
    self.azure_location = self.azure_location.lower()
    self.azure_subscription_id = self.azure_subscription_id.lower()
    self.azure_client_id = self.azure_client_id.lower()
    self.azure_password = self.azure_password.lower()
    self.azure_tenant_id = self.azure_tenant_id.lower()

    if self.azure_resource_group and not resource_group_regex.match( self.azure_resource_group ):
      errors[ 'azure_resource_group' ] = '"{0}" is invalid'.format( self.azure_resource_group )

    if self.azure_subscription_id and not uuid_regex.match( self.azure_subscription_id ):
      errors[ 'azure_subscription_id' ] = '"{0}" is invalid'.format( self.azure_subscription_id )

    if self.azure_client_id and not uuid_regex.match( self.azure_client_id ):
      errors[ 'azure_client_id' ] = '"{0}" is invalid'.format( self.azure_client_id )

    if self.azure_password and not uuid_regex.match( self.azure_password ):
      errors[ 'azure_password' ] = '"{0}" is invalid'.format( self.azure_password )

    if self.azure_tenant_id and not uuid_regex.match( self.azure_tenant_id ):
      errors[ 'azure_tenant_id' ] = '"{0}" is invalid'.format( self.azure_tenant_id )

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'AzureComplex {0}'.format( self.pk )


def _vmSpec( foundation ):
  result = {}

  if foundation.structure is None:
    raise ValueError( 'No Structure Attached' )

  structure_config = getConfig( foundation.structure )
  structure_config = mergeValues( structure_config )

  result[ 'azure_size' ] = structure_config.get( 'azure_size', 'Standard_D1_v2' )

  for key in ( 'azure_admin_username', 'azure_admin_password', 'azure_image' ):
    try:
      result[ key ] = structure_config[ key ]
    except KeyError:
      pass

  return result


@cinp.model( property_list=( 'state', 'type', 'class_list' ) )
class AzureFoundation( Foundation ):
  azure_complex = models.ForeignKey( AzureComplex, on_delete=models.PROTECT )
  azure_resource_name = models.CharField( max_length=64, blank=True, null=True )

  @staticmethod
  def getTscriptValues( write_mode=False ):
    result = super( AzureFoundation, AzureFoundation ).getTscriptValues( write_mode )

    result[ 'azure_complex' ] = ( lambda foundation: foundation.azure_complex, None )
    result[ 'azure_resource_name' ] = ( lambda foundation: foundation.azure_resource_name, None )
    result[ 'azure_vmspec'] = ( lambda foundation: _vmSpec( foundation ), None )

    if write_mode is True:
      result[ 'azure_resource_name' ] = ( result[ 'azure_resource_name' ][0], lambda foundation, val: setattr( foundation, 'azure_resource_name', val ) )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( AzureFoundation, AzureFoundation ).getTscriptFunctions()
    result[ 'power_on' ] = lambda foundation: ( 'azure', set_power( foundation, 'on' ) )
    result[ 'power_off' ] = lambda foundation: ( 'azure', set_power( foundation, 'off' ) )
    result[ 'power_state' ] = lambda foundation: ( 'azure', power_state( foundation ) )
    result[ 'destroy' ] = lambda foundation: ( 'azure', destroy( foundation ) )

    return result

  def configAttributes( self ):
    result = super().configAttributes()
    result.update( { '_azure_resource_name': self.azure_resource_name } )
    result.update( { '_azure_complex': self.azure_complex.name } )
    result.update( { '_azure_resource_group': self.azure_complex.azure_resource_group } )
    result.update( { '_azure_location': self.azure_complex.azure_location } )

    return result

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'Azure'

  @property
  def class_list( self ):
    return [ 'VM', 'Azure' ]

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return AzureFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if self.pk is not None:
      current = AzureFoundation.objects.get( pk=self.pk )
      if ( self.azure_resource_name is not None or current.azure_resource_name is not None ) and current.azure_complex != self.azure_complex:
        errors[ 'azure_complex' ] = 'can not move complexes without first destroying'

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'AzureFoundation {0}'.format( self.pk )
