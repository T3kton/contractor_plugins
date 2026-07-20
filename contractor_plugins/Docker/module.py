import re

from contractor.tscript.runner import ExternalFunction, ParameterError
from contractor.Utilities.models import Address


NAME_REGEX = re.compile( r'^[a-zA-Z][a-zA-Z0-9\.\-_]*$' )


# exported functions
class create( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.connection_parameters = {}
    self.complete = False
    self.docker_id = None
    self.in_rollback = False
    self.docker_parameters = {}

  @property
  def done( self ):
    return self.complete is True

  @property
  def message( self ):
    if self.complete is True:
      if self.in_rollback:
        return 'Container Rolled Back'
      else:
        return 'Container Created'

    else:
      if self.in_rollback:
        return 'Container for Resource Rollback'
      else:
        return 'Container for Resource Creation'

  @property
  def value( self ):
    return { 'docker_id': self.docker_id }

  def setup( self, parms ):
    try:
      container_spec = parms[ 'container_spec' ]
    except KeyError:
      raise ParameterError( 'container_spec', 'required' )

    try:
      port_map = parms[ 'port_map' ]
    except KeyError:
      raise ParameterError( 'port_map', 'required' )

    try:
      name = self.getScriptValue( 'foundation', 'locator' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation Locator: {0}'.format( e ) )

    if not NAME_REGEX.match( name ):
      raise ParameterError( '<internal>', 'invalid name (ie: Foundation Locator)' )

    try:
      docker_complex = self.getScriptValue( 'foundation', 'docker_complex' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation docker_complex: {0}'.format( e ) )

    self.connection_parameters = docker_complex.connection_parameters

    self.docker_parameters = {
                               'name': name,
                               'docker_image': container_spec[ 'image' ],
                               'port_map': port_map,
                               'environment_map': container_spec.get( 'environment_map', {} ),
                               'command': container_spec.get( 'command', None )
                              }

  def toSubcontractor( self ):
    parameters = self.docker_parameters.copy()
    parameters.update( { 'connection': self.connection_parameters } )

    if self.in_rollback:
      return ( 'create_rollback', parameters )
    else:
      return ( 'create', parameters )

  def fromSubcontractor( self, data ):  # TODO: really if these are missing or false, there is a problem
    if self.in_rollback:
      self.in_rollback = not data.get( 'rollback_done', False )
    else:
      self.complete = data.get( 'done', False )
      self.docker_id = data.get( 'id', None )

  def rollback( self ):
    self.in_rollback = True

  def __getstate__( self ):
    return ( self.connection_parameters, self.complete, self.in_rollback, self.docker_id, self.docker_parameters )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.complete = state[1]
    self.in_rollback = state[2]
    self.docker_id = state[3]
    self.docker_parameters = state[4]


# other functions used by the virtualbox foundation
class destroy( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.docker_id = foundation.docker_id
    self.name = foundation.locator
    self.connection_parameters = foundation.docker_complex.connection_parameters
    self.complete = None

  @property
  def done( self ):
    return self.complete is True

  @property
  def message( self ):
    if self.complete is True:
      return 'Container Destroyed'
    else:
      return 'Waiting for Container Destruction'

  def toSubcontractor( self ):
    return ( 'destroy', { 'connection': self.connection_parameters, 'docker_id': self.docker_id, 'name': self.name } )

  def fromSubcontractor( self, data ):
    self.complete = True

  def __getstate__( self ):
    return ( self.connection_parameters, self.complete, self.docker_id, self.name )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.complete = state[1]
    self.docker_id = state[2]
    self.name = state[3]


class map_ports( object ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.foundation = foundation
    self.complex = foundation.complex
    self.structure = foundation.structure

  def __call__( self, container_spec ):
    port_list = container_spec[ 'port_list' ]
    port_map = {}
    check_port = None
    aviable_ports = self.complex.dockerport_set.select_for_update().filter( foundation__isnull=True )[ :len( port_list ) ]
    if len( aviable_ports ) < len( port_list ):
      raise Exception( 'Insufficient DockerPorts are Available' )

    for i in range( 0, len( port_list ) ):
      dp = aviable_ports[i]
      dp.foundation = self.foundation
      dp.foundation_index = i
      dp.full_clean()
      dp.save()

      port_map[ port_list[ i ] ] = dp.port
      if check_port is None:
        check_port = dp.port

        addr = Address( networked=self.structure, pointer=dp.address, interface_name='eth0', is_primary=True )
        addr.full_clean()
        addr.save()

    self.structure.config_values[ 'docker_port_map' ] = port_map
    self.structure.config_values[ 'docker_check_port' ] = check_port
    self.structure.full_clean()
    self.structure.save()

    return port_map


class unmap_ports( object ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.foundation = foundation

  def __call__( self ):
    for port in self.foundation.dockerport_set.all():
      port.foundation = None
      port.foundation_index = 0
      port.full_clean()
      port.save()


class start_stop( ExternalFunction ):  # TODO: need a delay after each power command, at least 5 seconds, last ones could possibly be longer
  def __init__( self, foundation, state, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.docker_id = foundation.docker_id
    self.name = foundation.locator
    self.connection_parameters = foundation.docker_complex.connection_parameters
    self.desired_state = state
    self.curent_state = None
    self.sent = False

  def run( self ):
    pass

  @property
  def done( self ):
    return self.desired_state == self.curent_state

  @property
  def message( self ):
    return 'State curently "{0}" waiting for "{1}"'.format( self.curent_state, self.desired_state )

  def rollback( self ):
    self.curent_state = None

  def toSubcontractor( self ):
    return ( 'start_stop', { 'connection': self.connection_parameters, 'state': self.desired_state, 'docker_id': self.docker_id, 'name': self.name, 'sent': self.sent } )

  def fromSubcontractor( self, data ):
    self.curent_state = data[ 'state' ]
    self.sent = True

  def __getstate__( self ):
    return ( self.connection_parameters, self.docker_id, self.name, self.desired_state, self.curent_state, self.sent )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.docker_id = state[1]
    self.name = state[2]
    self.desired_state = state[3]
    self.curent_state = state[4]
    self.sent = state[5]


class state( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.docker_id = foundation.docker_id
    self.name = foundation.locator
    self.connection_parameters = foundation.docker_complex.connection_parameters
    self.state = None

  @property
  def done( self ):
    return self.state is not None

  @property
  def message( self ):
    if self.state is None:
        return 'Retrieving for State'

    return 'State at "{0}"'.format( self.state )

  @property
  def value( self ):
    return self.state

  def toSubcontractor( self ):
    return ( 'state', { 'connection': self.connection_parameters, 'docker_id': self.docker_id, 'name': self.name } )

  def fromSubcontractor( self, data ):
    self.state = data[ 'state' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.docker_id, self.state, self.name )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.docker_id = state[1]
    self.state = state[2]
    self.name = state[3]


# plugin exports

TSCRIPT_NAME = 'docker'

TSCRIPT_FUNCTIONS = {
                      'create': create,
                    }

TSCRIPT_VALUES = {
                 }
