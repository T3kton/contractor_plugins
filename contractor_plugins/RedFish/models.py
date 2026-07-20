from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, FOUNDATION_SUBCLASS_LIST
from contractor.Survey.models import Plot
# from contractor.Utilities.models import RealNetworkInterface, Networked
from contractor.Foreman.lib import RUNNER_MODULE_LIST

from contractor_plugins.RedFish.module import link_test, set_power, power_state, wait_for_poweroff

cinp = CInP( 'RedFish', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'redfishfoundation' )
RUNNER_MODULE_LIST.append( 'contractor_plugins.RedFish.module' )


@cinp.model( property_list=( 'state', 'type', 'class_list' ) )
class RedFishFoundation( Foundation ):  # , Networked ):
  SOL_PORT_CHOICES = ( 'console', 'ttyS0', 'ttyS1', 'ttyS2', 'ttyS3' )
  redfish_username = models.CharField( max_length=50 )
  redfish_password = models.CharField( max_length=50 )
  # redfish_interface = models.ForeignKey( RealNetworkInterface )
  redfish_ip_address = models.CharField( max_length=30 )
  redfish_sol_port = models.CharField( max_length=7, choices=[ ( i, i ) for i in SOL_PORT_CHOICES ], default='ttyS1' )
  plot = models.ForeignKey( Plot, on_delete=models.PROTECT )

  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( RedFishFoundation, RedFishFoundation ).getTscriptValues( write_mode )

    # result[ 'redfish_ip_address' ] = ( lambda foundation: foundation.redfish_interface.ip_address, None )
    result[ 'redfish_ip_address' ] = ( lambda foundation: foundation.redfish_ip_address, None )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( RedFishFoundation, RedFishFoundation ).getTscriptFunctions()
    result[ 'link_test' ] = lambda foundation: ( 'redfish', link_test( foundation ) )
    result[ 'power_on' ] = lambda foundation: ( 'redfish', set_power( foundation, 'on' ) )
    result[ 'power_off' ] = lambda foundation: ( 'redfish', set_power( foundation, 'off' ) )
    result[ 'power_state' ] = lambda foundation: ( 'redfish', power_state( foundation ) )
    result[ 'wait_for_poweroff' ] = lambda foundation: ( 'redfish', wait_for_poweroff( foundation ) )

    return result

  def configAttributes( self ):
    result = super().configAttributes()
    result[ 'redfish_ip_address' ] = self.redfish_ip_address

    return result

  @property
  def console( self ):
    return self.redfish_sol_port

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'RedFish'

  @property
  def connection_parameters( self ):
    if self.redfish_password == '_VAULT_':
      creds = self.redfish_username

    else:
      creds = {
                'password': self.redfish_password,
                'username': self.redfish_username,
              }

    return {
              'ip_address': self.redfish_ip_address,
              'credentials': creds
            }

  @property
  def class_list( self ):
    return [ 'Physical', 'RedFish' ]

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return RedFishFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if errors:
      if self.port not in RedFishFoundation.SOL_PORT_CHOICES:
        errors[ 'port' ] = 'Invalid'

      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'RedFishFoundation {0}'.format( self.pk )
