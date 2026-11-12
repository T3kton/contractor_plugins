from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, Complex, FOUNDATION_SUBCLASS_LIST, COMPLEX_SUBCLASS_LIST
from contractor.BluePrint.models import FoundationBluePrint

from contractor_plugins.Test.module import PowerOperation

cinp = CInP( 'Test', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'testfoundation' )
FOUNDATION_SUBCLASS_LIST.append( 'testcomplexedfoundation' )
COMPLEX_SUBCLASS_LIST.append( 'testcomplex' )


@cinp.model( property_list=( 'state', 'type' ) )
class TestComplex( Complex ):
  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'Test'

  def newFoundation( self, hostname, site ):
    foundation = TestComplexedFoundation( site=site, blueprint=FoundationBluePrint.objects.get( pk='test-foundation-base' ), locator=hostname )
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
    return 'TestComplex {0}'.format( self.pk )


@cinp.model( property_list=( 'state', 'type', 'class_list' ) )
class TestFoundation( Foundation ):
  test_delay_variance = models.IntegerField( default=30, help_text='In Seconds' )
  test_fail_likelihood = models.IntegerField( default=0, help_text='Likelyhood of failures per 1000, per "run" execution (ie: the longer the delay the more likely), if greater than 9, Unrecoverable errors my happen, 0 to disable' )

  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( TestFoundation, TestFoundation ).getTscriptValues( write_mode )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( TestFoundation, TestFoundation ).getTscriptFunctions()
    result[ 'power_on' ] = lambda foundation: ( 'test', PowerOperation( foundation, 'power_on' ) )
    result[ 'power_off' ] = lambda foundation: ( 'test', PowerOperation( foundation, 'power_off' ) )
    result[ 'power_state' ] = lambda foundation: ( 'test', PowerOperation( foundation, 'power_state' ) )
    result[ 'wait_for_poweroff' ] = lambda foundation: ( 'test', PowerOperation( foundation, 'wait_for_poweroff' ) )

    return result

  def configAttributes( self ):
    result = super().configAttributes()

    return result

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'Test'

  @property
  def class_list( self ):
    return [ 'Metal', 'VM', 'Container', 'Switch', 'Manual', 'Test' ]

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return TestFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'TestFoundation {0}'.format( self.pk )


@cinp.model( property_list=( 'state', 'type', 'class_list' ) )
class TestComplexedFoundation( Foundation ):
  complex_host = models.ForeignKey( TestComplex, on_delete=models.PROTECT )

  def configAttributes( self ):
    result = super().configAttributes()
    result.update( { '_complex_host': self.complex_host.name } )

    return result

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'TestComplex'

  @property
  def class_list( self ):
    return [ 'TestComplex' ]

  @property
  def complex( self ):
    return self.complex_host

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return TestComplexedFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'TestComplexedFoundation {0}'.format( self.pk )
