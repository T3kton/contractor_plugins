from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from contractor.Site.models import Site
from contractor.Building.models import Foundation, Complex, FOUNDATION_SUBCLASS_LIST, COMPLEX_SUBCLASS_LIST
from contractor.Foreman.lib import RUNNER_MODULE_LIST
from contractor.BluePrint.models import FoundationBluePrint
from contractor.lib.config import getConfig, mergeValues

from contractor_plugins.Docker.module import start_stop, state, destroy, map_ports, unmap_ports

cinp = CInP( 'Docker', '0.1' )

FOUNDATION_SUBCLASS_LIST.append( 'dockerfoundation' )
COMPLEX_SUBCLASS_LIST.append( 'dockercomplex' )
RUNNER_MODULE_LIST.append( 'contractor_plugins.Docker.module' )


@cinp.model( property_list=( 'state', 'type' ) )
class DockerComplex( Complex ):
  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'Docker'

  @property
  def connection_parameters( self ):
    return {
              'host': self.members.get().primary_address.ip_address
            }

  def newFoundation( self, hostname, site ):
    foundation = DockerFoundation( site=site, blueprint=FoundationBluePrint.objects.get( pk='docker-continaer-base' ), locator=hostname )
    foundation.docker_complex = self
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

    if self.pk is not None and self.members.count() > 1:
      errors[ 'structure' ] = 'Docker Complex support only one structure'

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'DockerComplex {0}'.format( self.pk )


def _containerSpec( foundation ):
  result = {}

  structure_config = getConfig( foundation.structure )
  structure_config = mergeValues( structure_config )

  result[ 'image' ] = structure_config[ 'docker_image' ]
  result[ 'port_list' ] = structure_config.get( 'port_list', [] )
  result[ 'environment_map' ] = structure_config.get( 'environment_map', {} )
  result[ 'command' ] = structure_config.get( 'docker_command', None )

  return result


@cinp.model( property_list=( 'state', 'type', 'class_list' ), read_only_list=[ 'docker_id' ] )
class DockerFoundation( Foundation ):
  docker_complex = models.ForeignKey( DockerComplex, on_delete=models.PROTECT )
  docker_id = models.CharField( max_length=64, blank=True, null=True )  # not going to do unique, there could be multiple docker hosts

  @staticmethod
  def getTscriptValues( write_mode=False ):  # locator is handled seperatly
    result = super( DockerFoundation, DockerFoundation ).getTscriptValues( write_mode )

    result[ 'docker_id' ] = ( lambda foundation: foundation.docker_id, None )
    result[ 'docker_complex' ] = ( lambda foundation: foundation.docker_complex, None )
    result[ 'docker_containerspec'] = ( lambda foundation: _containerSpec( foundation ), None )

    if write_mode is True:
      result[ 'docker_id' ] = ( result[ 'docker_id' ][0], lambda foundation, val: setattr( foundation, 'docker_id', val ) )

    return result

  @staticmethod
  def getTscriptFunctions():
    result = super( DockerFoundation, DockerFoundation ).getTscriptFunctions()
    result[ 'start' ] = lambda foundation: ( 'docker', start_stop( foundation, 'start' ) )
    result[ 'stop' ] = lambda foundation: ( 'docker', start_stop( foundation, 'stop' ) )
    result[ 'state' ] = lambda foundation: ( 'docker', state( foundation ) )
    result[ 'destroy' ] = lambda foundation: ( 'docker', destroy( foundation ) )
    result[ 'map_ports' ] = lambda foundation: map_ports( foundation )
    result[ 'unmap_ports' ] = lambda foundation: unmap_ports( foundation )

    return result

  def configAttributes( self ):
    result = super().configAttributes()
    result.update( { '_docker_id': self.docker_id } )
    result.update( { '_docker_complex': self.docker_complex.name } )

    return result

  @property
  def subclass( self ):
    return self

  @property
  def type( self ):
    return 'Docker'

  @property
  def class_list( self ):
    return [ 'Container', 'Docker' ]

  @property
  def complex( self ):
    return self.docker_complex

  @cinp.list_filter( name='site', parameter_type_list=[ { 'type': 'Model', 'model': Site } ] )
  @staticmethod
  def filter_site( site ):
    return DockerFoundation.objects.filter( site=site )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, method, id_list, action=None ):
    return super( __class__, __class__ ).checkAuth( user, method, id_list, action )

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if self.pk is not None:
      current = DockerFoundation.objects.get( pk=self.pk )
      if ( self.docker_id is not None or current.docker_id is not None ) and current.docker_complex != self.docker_complex:
        errors[ 'docker_complex' ] = 'can not move complexes without first destroying'

    if self.site.pk != self.docker_complex.site.pk:
      errors[ 'site' ] = 'Site must match the docker_complex\'s site'

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()

  def __str__( self ):
    return 'DockerFoundation {0}'.format( self.pk )


@cinp.model()
class DockerPort( models.Model ):
  complex = models.ForeignKey( DockerComplex, on_delete=models.CASCADE )
  port = models.IntegerField()
  address_offset = models.IntegerField()
  foundation = models.ForeignKey( DockerFoundation, on_delete=models.SET_NULL, blank=True, null=True )
  foundation_index = models.IntegerField( default=0 )
  updated = models.DateTimeField( editable=False, auto_now=True )
  created = models.DateTimeField( editable=False, auto_now_add=True )

  @property
  def address( self ):
    addr_set = self.complex.members.get().networked_ptr.address_set.order_by( 'is_primary' )
    try:
      return addr_set[ self.address_offset ]
    except KeyError:
      return None

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, verb, id_list, action=None ):
    return cinp.basic_auth_check( user, verb, action, DockerPort )

  def clean( self, *args, **kwargs ):  # TODO: do not allow port or address_offset to change, or find a way to make changes propagate
    super().clean( *args, **kwargs )
    errors = {}

    if self.port > 65535 and self.port < 4096:
      errors[ 'port' ] = 'must be from 4096 to 65535'

    if self.address_offset > 100 and self.address_offset < 0:
      errors[ 'address_offset' ] = 'must be from 0 to 100'

    if self.foundation is not None and self.complex != self.foundation.docker_complex:
      errors[ 'foundation' ] = 'Port\'s complex does not match the Foundation\'s complex'

    if errors:
      raise ValidationError( errors )

  class Meta:
    # default_permissions = ( 'add', 'change', 'delete', 'view' )
    unique_together = ( ( 'foundation', 'foundation_index' ), )

  def __str__( self ):
    return 'DockerPort {0}'.format( self.pk )
