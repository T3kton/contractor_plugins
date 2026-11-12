from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, FOUNDATION_SUBCLASS_LIST, CONSOLE_PORT_CHOICES
from contractor.Survey.models import Plot
# from contractor.Utilities.models import RealNetworkInterface, Networked
from contractor.Foreman.lib import RUNNER_MODULE_LIST

from contractor_plugins.IPMI.module import link_test, set_power, power_state, wait_for_poweroff

cinp = CInP( 'IPMI', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'ipmifoundation' )
RUNNER_MODULE_LIST.append( 'contractor_plugins.IPMI.module' )


@cinp.model( property_list=( 'state', 'type', 'class_list' ) )
class IPMIFoundation( Foundation ):  # , Networked ):
  SOL_PORT_CHOICES = CONSOLE_PORT_CHOICES
  ipmi_username = models.CharField( max_length=50 )
  ipmi_password = models.CharField( max_length=50 )
  # ipmi_interface = models.ForeignKey( RealNetworkInterface )
  ipmi_ip_address = models.CharField( max_length=30 )
  ipmi_sol_port = models.CharField( max_length=7, choices=[ ( i, i ) for i in SOL_PORT_CHOICES ], default='ttyS1' )
  plot = models.ForeignKey( Plot, on_delete=models.PROTECT )

  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( IPMIFoundation, IPMIFoundation ).getTscriptValues( write_mode )

    # result[ 'ipmi_ip_address' ] = ( lambda foundation: foundation.ipmi_interface.ip_address, None )
    result[ 'ipmi_ip_address' ] = ( lambda foundation: foundation.ipmi_ip_address, None )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( IPMIFoundation, IPMIFoundation ).getTscriptFunctions()
    result[ 'link_test' ] = lambda foundation: ( 'ipmi', link_test( foundation ) )
    result[ 'power_on' ] = lambda foundation: ( 'ipmi', set_power( foundation, 'on' ) )
    result[ 'power_off' ] = lambda foundation: ( 'ipmi', set_power( foundation, 'off' ) )
    result[ 'power_state' ] = lambda foundation: ( 'ipmi', power_state( foundation ) )
    result[ 'wait_for_poweroff' ] = lambda foundation: ( 'ipmi', wait_for_poweroff( foundation ) )

    return result

  def configAttributes( self ):
    result = super().configAttributes()
    result[ 'ipmi_ip_address' ] = self.ipmi_ip_address

    return result

  @property
  def console( self ):
    return self.ipmi_sol_port

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'IPMI'

  @property
  def connection_parameters( self ):
    if self.ipmi_password == '_VAULT_':
      creds = self.ipmi_username

    else:
      creds = {
                'password': self.ipmi_password,
                'username': self.ipmi_username,
              }

    return {
              'ip_address': self.ipmi_ip_address,
              'credentials': creds
            }

  @property
  def class_list( self ):
    return [ 'Physical', 'IPMI' ]

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return IPMIFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if errors:
      if self.port not in IPMIFoundation.SOL_PORT_CHOICES:
        errors[ 'port' ] = 'Invalid'

      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'IPMIFoundation {0}'.format( self.pk )
