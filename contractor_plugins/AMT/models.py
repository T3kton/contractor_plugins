from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, FOUNDATION_SUBCLASS_LIST
from contractor.Survey.models import Plot
# from contractor.Utilities.models import RealNetworkInterface, Networked
from contractor.Foreman.lib import RUNNER_MODULE_LIST

from contractor_plugins.AMT.module import set_power, power_state, wait_for_poweroff

cinp = CInP( 'AMT', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'amtfoundation' )
RUNNER_MODULE_LIST.append( 'contractor_plugins.AMT.module' )


@cinp.model( property_list=( 'state', 'type', 'class_list' ) )
class AMTFoundation( Foundation ):  # , Networked ):
  amt_username = models.CharField( max_length=50, default='admin' )
  amt_password = models.CharField( max_length=50 )
  # amt_interface = models.ForeignKey( RealNetworkInterface )
  amt_ip_address = models.CharField( max_length=30 )
  plot = models.ForeignKey( Plot, on_delete=models.PROTECT )

  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( AMTFoundation, AMTFoundation ).getTscriptValues( write_mode )

    # result[ 'amt_ip_address' ] = ( lambda foundation: foundation.amt_interface.ip_address, None )
    result[ 'amt_ip_address' ] = ( lambda foundation: foundation.amt_ip_address, None )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( AMTFoundation, AMTFoundation ).getTscriptFunctions()
    result[ 'power_on' ] = lambda foundation: ( 'amt', set_power( foundation, 'on' ) )
    result[ 'power_off' ] = lambda foundation: ( 'amt', set_power( foundation, 'off' ) )
    result[ 'power_state' ] = lambda foundation: ( 'amt', power_state( foundation ) )
    result[ 'wait_for_poweroff' ] = lambda foundation: ( 'amt', wait_for_poweroff( foundation ) )

    return result

  def configAttributes( self ):
    result = super().configAttributes()

    return result

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'AMT'

  @property
  def connection_parameters( self ):
    if self.amt_password == '_VAULT_':
      creds = self.amt_username

    else:
      creds = {
                'password': self.amt_password,
                'username': self.amt_username,
              }
    return {
              'ip_address': self.amt_ip_address,
              'credentials': creds
            }

  @property
  def class_list( self ):
    return [ 'Physical', 'AMT' ]

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return AMTFoundation.objects.filter( site=site )

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
    return 'AMTFoundation {0}'.format( self.pk )
