import re

from contractor.tscript.runner import ExternalFunction, ParameterError

NAME_REGEX = re.compile( r'^[a-zA-Z][a-zA-Z0-9\-_]*$' )


# exported functions
class create( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.resource_name = None
    self.resource_group = None
    self.location = None
    self.in_rollback = False
    self.connection_parameters = {}
    self.vm_parameters = {}

  @property
  def done( self ):
    return self.resource_name is not None

  @property
  def message( self ):
    if self.resource_name is not None:
      if self.in_rollback:
        return 'Resource Rolled Back'
      else:
        return 'Resource Created'

    else:
      if self.in_rollback:
        return 'Waiting for Resource Rollback'
      else:
        return 'Waiting for Resource Creation'

  @property
  def value( self ):
    return self.resource_name

  def setup( self, parms ):
    try:
      foundation = self.getScriptValue( 'foundation', 'foundation' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation: {0}'.format( e ) )

    try:
      azure_complex = self.getScriptValue( 'foundation', 'azure_complex' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation azure_complex: {0}'.format( e ) )

    self.connection_parameters = azure_complex.connection_parameters
    self.resource_group = azure_complex.azure_resource_group
    self.location = azure_complex.azure_location

    try:
      vm_name = self.getScriptValue( 'foundation', 'locator' )
    except KeyError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation Locator: {0}'.format( e ) )

    if not NAME_REGEX.match( vm_name ):
      raise ParameterError( '<internal>', 'invalid name (ie: Foundation Locator)' )

    try:
      vm_spec = parms[ 'vm_spec' ]
    except KeyError:
      raise ParameterError( 'vm_spec', 'required' )

    if not isinstance( vm_spec, dict ):
      raise ParameterError( 'vm_spec', 'must be a dict' )

    self.vm_parameters = {}
    self.vm_parameters[ 'name' ] = vm_name

    interface_list = []
    for interface in foundation.networkinterface_set.all().order_by( 'physical_location' ):
      nic_name = '{0}-{1}'.format( vm_name, interface.name )
      config_list = []
      counter = 0
      for address in interface.config[ 'address_list' ]:
        config_list.append( {
                              'name': '{0}-ipconfig-{1}'.format( nic_name, counter ),
                              'address': address[ 'address' ]
                            } )
        counter += 1

      interface_list.append( {
                                'name': '{0}-nic'.format( nic_name ),
                                'network': interface.network.name,
                                'config_list': config_list
                              } )

    self.vm_parameters[ 'interface_list' ] = interface_list
    self.vm_parameters[ 'admin' ] = { 'username': vm_spec[ 'azure_admin_username' ], 'password': vm_spec[ 'azure_admin_password' ] }

    for key in ( 'azure_size', 'azure_image' ):
      try:
        self.vm_parameters[ key[ 6: ] ] = vm_spec[ key ]
      except KeyError:
        pass

    if 'image' in self.vm_parameters and set( self.vm_parameters[ 'image' ].keys() ) != set( [ 'publisher', 'offer', 'sku', 'version' ] ):
      raise ValueError( 'azure_image defination is invalid' )

  def toSubcontractor( self ):
    if self.in_rollback:
      return ( 'create_rollback', { 'connection': self.connection_parameters, 'vm': self.vm_parameters, 'resource_group': self.resource_group } )
    else:
      return ( 'create', { 'connection': self.connection_parameters, 'vm': self.vm_parameters, 'resource_group': self.resource_group, 'location': self.location } )

  def fromSubcontractor( self, data ):  # TODO: really if these are missing or false, there is a problem
    if self.in_rollback:
      self.in_rollback = not data.get( 'rollback_done', False )

    else:
      self.resource_name = data.get( 'resource_name', None )

  def rollback( self ):
    self.in_rollback = True

  def __getstate__( self ):
    return ( self.connection_parameters, self.vm_parameters, self.in_rollback, self.resource_name, self.resource_group, self.location )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.vm_parameters = state[1]
    self.in_rollback = state[2]
    self.resource_name = state[3]
    self.resource_group = state[4]
    self.location = state[5]


# other functions used by the azure foundation
class destroy( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.resource_name = foundation.azure_resource_name
    self.resource_group = foundation.azure_complex.azure_resource_group
    self.connection_parameters = foundation.azure_complex.connection_parameters
    self.completed = None

  @property
  def done( self ):
    return self.completed is True

  @property
  def message( self ):
    if self.completed is True:
      return 'Resource Destroyed'
    else:
      return 'Waiting for Resource Destruction'

  def toSubcontractor( self ):
    return ( 'destroy', { 'connection': self.connection_parameters, 'resource_name': self.resource_name, 'resource_group': self.resource_group } )

  def fromSubcontractor( self, data ):
    self.completed = True

  def __getstate__( self ):
    return ( self.connection_parameters, self.resource_name, self.resource_group, self.completed )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.resource_name = state[1]
    self.resource_group = state[2]
    self.completed = state[3]


class set_power( ExternalFunction ):  # TODO: need a delay after each power command, at least 5 seconds, last ones could possibly be longer
  def __init__( self, foundation, state, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.resource_name = foundation.azure_resource_name
    self.resource_group = foundation.azure_complex.azure_resource_group
    self.connection_parameters = foundation.azure_complex.connection_parameters
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
    return 'Power curently "{0}" waiting for "{1}"'.format( self.curent_state, self.desired_state )

  def rollback( self ):
    self.curent_state = None

  def toSubcontractor( self ):
    return ( 'set_power', { 'connection': self.connection_parameters, 'state': self.desired_state, 'resource_name': self.resource_name, 'resource_group': self.resource_group, 'sent': self.sent } )

  def fromSubcontractor( self, data ):
    self.curent_state = data[ 'state' ]
    self.sent = True

  def __getstate__( self ):
    return ( self.connection_parameters, self.resource_name, self.resource_group, self.desired_state, self.curent_state, self.sent )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.resource_name = state[1]
    self.resource_group = state[2]
    self.desired_state = state[3]
    self.curent_state = state[4]
    self.sent = state[5]


class power_state( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.resource_name = foundation.azure_resource_name
    self.resource_group = foundation.azure_complex.azure_resource_group
    self.connection_parameters = foundation.azure_complex.connection_parameters
    self.state = None

  @property
  def done( self ):
    return self.state is not None

  @property
  def message( self ):
    if self.state is None:
        return 'Retrieving for Power State'

    return 'Power State at "{0}"'.format( self.state )

  @property
  def value( self ):
    return self.state

  def toSubcontractor( self ):
    return ( 'power_state', { 'connection': self.connection_parameters, 'resource_name': self.resource_name, 'resource_group': self.resource_group } )

  def fromSubcontractor( self, data ):
    self.state = data[ 'state' ]

  def __getstate__( self ):
    return ( self.connection_parameters, self.resource_name, self.resource_group, self.state )

  def __setstate__( self, state ):
    self.connection_parameters = state[0]
    self.resource_name = state[1]
    self.resource_group = state[2]
    self.state = state[3]


# plugin exports

TSCRIPT_NAME = 'azure'

TSCRIPT_FUNCTIONS = {
                      'create': create,
                    }

TSCRIPT_VALUES = {
                 }
