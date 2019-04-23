import re
from django.core.exceptions import ObjectDoesNotExist, ValidationError

from contractor.tscript.runner import ExternalFunction, ParamaterError
from contractor.Utilities.models import ipAddress2Native, Address

NAME_REGEX = re.compile( '^[a-zA-Z][a-zA-Z0-9\-_]*$' )


# exported functions
class create( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.resource_name = None
    self.in_rollback = False
    self.connection_paramaters = {}
    self.vm_paramaters = {}

  @property
  def ready( self ):
    if self.done is True:
      return True

    else:
      if self.in_rollback:
        return 'Waiting for Resource Rollback'
      else:
        return 'Waiting for Resource Creation'

  @property
  def value( self ):
    return { 'resource_name': self.resource_name }

  def setup( self, parms ):
    try:
      foundation = self.getScriptValue( 'foundation', 'foundation' )
    except ValueError as e:
      raise ParamaterError( '<internal>', 'Unable to get Foundation: {0}'.format( e ) )

    try:
      azure_cluster = self.getScriptValue( 'foundation', 'azure_cluster' )
    except ValueError as e:
      raise ParamaterError( '<internal>', 'Unable to get Foundation azure_cluster: {0}'.format( e ) )

    self.connection_paramaters = azure_cluster.connection_paramaters

    try:
      vm_name = self.getScriptValue( 'foundation', 'locator' )
    except KeyError as e:
      raise ParamaterError( '<internal>', 'Unable to get Foundation Locator: {0}'.format( e ) )

    if not NAME_REGEX.match( vm_name ):
      raise ParamaterError( '<internal>', 'invalid name (ie: Foundation Locator)' )

    try:
      vm_spec = parms[ 'vm_spec' ]
    except KeyError:
      raise ParamaterError( 'vm_spec', 'required' )

    if not isinstance( vm_spec, dict ):
      raise ParamaterError( 'vm_spec', 'must be a dict' )

    self.vm_paramaters = {}
    self.vm_paramaters[ 'name' ] = vm_name
    self.vm_paramaters[ 'size' ] = vm_spec[ 'size' ]

    interface_list = []
    for interface in foundation.networkinterface_set.all().order_by( 'physical_location' ):
      name_map = interface.addressblock_name_map
      if not name_map:
        raise ParamaterError( '<internal>', 'addressblock name maping is empty for interface "{0}"'.format( interface.name ) )

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
                                'network': name_map[ None ],
                                'config_list': config_list
                              } )

    self.vm_paramaters[ 'interface_list' ] = interface_list
    self.vm_paramaters[ 'admin' ] = { 'username': vm_spec[ 'azure_admin_username' ], 'password': vm_spec[ 'azure_admin_password' ] }

    for key in ( 'azure_resource_group', 'azure_location', 'azure_image' ):
      try:
        self.vm_paramaters[ key[ 6: ] ] = vm_spec[ key ]
      except KeyError:
        pass

    if 'image' in self.vm_paramaters and set( self.vm_paramaters[ 'azure_image' ].keys() ) != set( [ 'publisher', 'offer', 'sku', 'version' ] ):
      raise ValueError( 'azure_image defination is invalid' )

  def toSubcontractor( self ):
    if self.in_rollback:
      return ( 'create_rollback', { 'connection': self.connection_paramaters, 'vm': self.vm_paramaters } )
    else:
      return ( 'create', { 'connection': self.connection_paramaters, 'vm': self.vm_paramaters } )

  def fromSubcontractor( self, data ):  # TODO: really if these are missing or false, there is a problem
    if self.in_rollback:
      self.in_rollback = not data.get( 'rollback_done', False )
    else:
      self.done = data.get( 'done', False )
      self.resource_name = data.get( 'resource_name', None )

  def rollback( self ):
    self.in_rollback = True

  def __getstate__( self ):
    return ( self.connection_paramaters, self.vm_paramaters, self.in_rollback, self.resource_name )

  def __setstate__( self, state ):
    self.connection_paramaters = state[0]
    self.vm_paramaters = state[1]
    self.in_rollback = state[2]
    self.resource_name = state[3]


# other functions used by the azure foundation
class destroy( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.resource_name = foundation.azure_resource_name
    self.connection_paramaters = foundation.azure_cluster.connection_paramaters
    self.done = None

  @property
  def ready( self ):
    if self.done is True:
      return True
    else:
      return 'Waiting for Resource Destruction'

  def toSubcontractor( self ):
    return ( 'destroy', { 'connection': self.connection_paramaters, 'resource_name': self.resource_name } )

  def fromSubcontractor( self, data ):
    self.done = True

  def __getstate__( self ):
    return ( self.connection_paramaters, self.resource_name, self.done )

  def __setstate__( self, state ):
    self.connection_paramaters = state[0]
    self.resource_name = state[1]
    self.done = state[2]


class set_power( ExternalFunction ):  # TODO: need a delay after each power command, at least 5 seconds, last ones could possibly be longer
  def __init__( self, foundation, state, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.resource_name = foundation.azure_resource_name
    self.connection_paramaters = foundation.azure_cluster.connection_paramaters
    self.desired_state = state
    self.curent_state = None
    self.sent = False

  def run( self ):
    pass

  @property
  def ready( self ):
    if self.desired_state == self.curent_state:
      return True
    else:
      return 'Power curently "{0}" waiting for "{1}"'.format( self.curent_state, self.desired_state )

  def rollback( self ):
    self.curent_state = None

  def toSubcontractor( self ):
    return ( 'set_power', { 'connection': self.connection_paramaters, 'state': self.desired_state, 'resource_name': self.resource_name, 'sent': self.sent } )

  def fromSubcontractor( self, data ):
    self.curent_state = data[ 'state' ]
    self.sent = True

  def __getstate__( self ):
    return ( self.connection_paramaters, self.resource_name, self.desired_state, self.curent_state, self.sent )

  def __setstate__( self, state ):
    self.connection_paramaters = state[0]
    self.resource_name = state[1]
    self.desired_state = state[2]
    self.curent_state = state[3]
    self.sent = state[4]


class power_state( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.resource_name = foundation.azure_resource_name
    self.connection_paramaters = foundation.azure_cluster.connection_paramaters
    self.state = None

  @property
  def ready( self ):
    if self.state is not None:
      return True
    else:
      return 'Retrieving for Power State'

  @property
  def value( self ):
    return self.state

  def toSubcontractor( self ):
    return ( 'power_state', { 'connection': self.connection_paramaters, 'resource_name': self.resource_name } )

  def fromSubcontractor( self, data ):
    self.state = data[ 'state' ]

  def __getstate__( self ):
    return ( self.connection_paramaters, self.resource_name, self.state )

  def __setstate__( self, state ):
    self.connection_paramaters = state[0]
    self.resource_name = state[1]
    self.state = state[2]


# plugin exports

TSCRIPT_NAME = 'azure'

TSCRIPT_FUNCTIONS = {
                      'create': create,
                    }

TSCRIPT_VALUES = {
                 }
