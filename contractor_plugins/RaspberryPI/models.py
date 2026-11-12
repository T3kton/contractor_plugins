from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, FOUNDATION_SUBCLASS_LIST

cinp = CInP( 'RaspberryPi', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'raspberryPifoundation' )


@cinp.model( property_list=( 'state', 'type', 'class_list' ) )
class RaspberryPiFoundation( Foundation ):
  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'RaspberryPi'

  @property
  def class_list( self ):
    return [ 'Metal', 'Manual', 'RaspberryPi' ]

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return RaspberryPiFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'RaspberryPiFoundation {0}'.format( self.pk )
