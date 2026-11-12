from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, Complex, FOUNDATION_SUBCLASS_LIST, COMPLEX_SUBCLASS_LIST
from contractor.BluePrint.models import FoundationBluePrint

from contractor_plugins.Manual.module import set_power, power_state, wait_for_poweroff

cinp = CInP( 'Manual', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'manualfoundation' )
FOUNDATION_SUBCLASS_LIST.append( 'manualcomplexedfoundation' )
COMPLEX_SUBCLASS_LIST.append( 'manualcomplex' )


@cinp.model( property_list=( 'state', 'type' ) )
class ManualComplex( Complex ):
  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'Manual'

  def newFoundation( self, hostname, site ):
    foundation = ManualComplexedFoundation( site=site, blueprint=FoundationBluePrint.objects.get( pk='manual-foundation-base' ), locator=hostname )
    foundation.complex_host = self
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
    return 'ManualComplex {0}'.format( self.pk )


@cinp.model( property_list=( 'state', 'type', 'class_list' ) )
class ManualFoundation( Foundation ):
  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( ManualFoundation, ManualFoundation ).getTscriptValues( write_mode )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( ManualFoundation, ManualFoundation ).getTscriptFunctions()
    result[ 'power_on' ] = lambda foundation: ( 'manual', set_power( foundation, 'on' ) )
    result[ 'power_off' ] = lambda foundation: ( 'manual', set_power( foundation, 'off' ) )
    result[ 'power_state' ] = lambda foundation: ( 'manual', power_state( foundation ) )
    result[ 'wait_for_poweroff' ] = lambda foundation: ( 'manual', wait_for_poweroff( foundation ) )

    return result

  def configAttributes( self ):
    result = super().configAttributes()

    return result

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'Manual'

  @property
  def class_list( self ):
    return [ 'Metal', 'VM', 'Container', 'Switch', 'Manual' ]

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return ManualFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'ManualFoundation {0}'.format( self.pk )


@cinp.model( property_list=( 'state', 'type', 'class_list' ) )
class ManualComplexedFoundation( Foundation ):
  complex_host = models.ForeignKey( ManualComplex, on_delete=models.PROTECT )

  def configAttributes( self ):
    result = super().configAttributes()
    result.update( { '_complex_host': self.complex_host.name } )

    return result

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'ManualComplex'

  @property
  def class_list( self ):
    return [ 'ManualComplex' ]

  @property
  def complex( self ):
    return self.complex_host

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return ManualComplexedFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'ManualComplexedFoundation {0}'.format( self.pk )
