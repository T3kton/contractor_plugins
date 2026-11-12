from django.db import models

from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, FOUNDATION_SUBCLASS_LIST
from contractor.Foreman.lib import RUNNER_MODULE_LIST

from contractor_plugins.AWS.module import set_power, power_state, destroy, set_interface_macs, set_ip_addresses

cinp = CInP( 'AWS', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'awsec2foundation' )
RUNNER_MODULE_LIST.append( 'contractor_plugins.AWS.module' )


@cinp.model( property_list=( 'state', 'type', 'class_list' ) )
class AWSEC2Foundation( Foundation ):
  awsec2_instance_id = models.CharField( max_length=19, blank=True, null=True )  # not going to do unique, there could be multiple AWS accounts

  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( AWSEC2Foundation, AWSEC2Foundation ).getTscriptValues( write_mode )

    result[ 'awsec2_instance_id' ] = ( lambda foundation: foundation.awsec2_instance_id, None )

    if write_mode is True:
      result[ 'awsec2_instance_id' ] = ( result[ 'awsec2_instance_id' ][0], lambda foundation, val: setattr( foundation, 'awsec2_instance_id', val ) )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( AWSEC2Foundation, AWSEC2Foundation ).getTscriptFunctions()
    result[ 'power_on' ] = lambda foundation: ( 'aws', set_power( foundation, 'on' ) )
    result[ 'power_off' ] = lambda foundation: ( 'aws', set_power( foundation, 'off' ) )
    result[ 'power_state' ] = lambda foundation: ( 'aws', power_state( foundation ) )
    result[ 'destroy' ] = lambda foundation: ( 'aws', destroy( foundation ) )
    result[ 'set_interface_macs' ] = lambda foundation: set_interface_macs( foundation )
    result[ 'set_ip_addresses' ] = lambda foundation: set_ip_addresses( foundation )

    return result

  def configAttributes( self ):
    # structure_blueprint_config = self.structure.blueprint.getConfig()
    result = super().configAttributes()
    result.update( { '_awsec2_instance_id': self.awsec2_instance_id } )

    # try:
    #   result.update( { 'awsec2_image_id': structure_blueprint_config[ 'awsec2_image_id' ] } )
    # except KeyError:
    #   pass

    return result

  @property
  def subclass( self ):
    return self

  @property
  def state( self ):
    return 'built'

  @property
  def type( self ):
    return 'AWSEC2'

  @property
  def class_list( self ):
    return [ 'AWSEC2' ]

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return AWSEC2Foundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  class Meta:
    pass
    # default_permissions = ( 'add', 'change', 'delete', 'view' )

  def __str__( self ):
    return 'AWSEC2Foundation {0}'.format( self.pk )
