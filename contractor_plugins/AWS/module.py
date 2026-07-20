import re
from django.core.exceptions import ObjectDoesNotExist, ValidationError

from contractor.tscript.runner import ExternalFunction, ParameterError

from contractor.Utilities.models import ipAddress2Native, Address

NAME_REGEX = re.compile( r'^[a-zA-Z][a-zA-Z0-9\.\-_]*$' )


# exported functions
class create( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.completed = False
    self.instance_id = None
    self.interface_list = []
    self.ip_address_map = {}
    self.in_rollback = False
    self.instance_parameters = {}

  @property
  def done( self ):
    return self.completed is True

  @property
  def message( self ):
    if self.completed is True:
      if self.in_rollback:
        return 'Instance Rolled Back'
      else:
        return 'Instance Created'

    else:
      if self.in_rollback:
        return 'Waiting for Instance Rollback'
      else:
        return 'Waiting for Instance Creation'

  @property
  def value( self ):
    return { 'instance_id': self.instance_id, 'interface_list': self.interface_list, 'ip_address_map': self.ip_address_map }

  def setup( self, parms ):
    try:
      instance_type = self.getScriptValue( 'config', 'awsec2_type' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get awsec2_type: {0}'.format( e ) )

    try:
      image_id = self.getScriptValue( 'config', 'awsec2_image_id' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get awsec2_image_id: {0}'.format( e ) )

    try:
      name = self.getScriptValue( 'foundation', 'locator' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation Locator: {0}'.format( e ) )

    if not NAME_REGEX.match( name ):
      raise ParameterError( '<internal>', 'invalid name (ie: Foundation Locator)' )

    self.instance_parameters = {
                                 'name': name,
                                 'image_id': image_id,
                                 'instance_type': instance_type,
                                 'interface_list': [ { 'name': 'public' } ]  # name is name of network to attach to
                               }

  def toSubcontractor( self ):
    if self.in_rollback:
      return ( 'create_rollback', self.instance_parameters )
    else:
      return ( 'create', self.instance_parameters )

  def fromSubcontractor( self, data ):  # TODO: really if these are missing or false, there is a problem
    if self.in_rollback:
      self.in_rollback = not data.get( 'rollback_done', False )
    else:
      self.completed = data.get( 'done', False )
      self.instance_id = data.get( 'instance_id', None )
      self.interface_list = data.get( 'interface_list', [] )
      self.ip_address_map = data.get( 'ip_address_map', {} )

  def rollback( self ):
    self.in_rollback = True

  def __getstate__( self ):
    return ( self.completed, self.in_rollback, self.instance_id, self.interface_list, self.ip_address_map, self.instance_parameters )

  def __setstate__( self, state ):
    self.completed = state[0]
    self.in_rollback = state[1]
    self.instance_id = state[2]
    self.interface_list = state[3]
    self.ip_address_map = state[4]
    self.instance_parameters = state[5]


# other functions used by the aws foundation
class destroy( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.instance_id = foundation.awsec2_instance_id
    self.name = foundation.locator
    self.completed = None

  @property
  def done( self ):
    return self.completed is True

  @property
  def message( self ):
    if self.completed:
      return 'Instance Destroyed'
    else:
      return 'Waiting for Instance Destruction'

  def toSubcontractor( self ):
    return ( 'destroy', { 'instance_id': self.instance_id, 'name': self.name } )

  def fromSubcontractor( self, data ):
    self.completed = True

  def __getstate__( self ):
    return ( self.completed, self.instance_id, self.name )

  def __setstate__( self, state ):
    self.completed = state[0]
    self.instance_id = state[1]
    self.name = state[2]


class set_power( ExternalFunction ):  # TODO: need a delay after each power command, at least 5 seconds, last ones could possibly be longer
  def __init__( self, foundation, state, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.instance_id = foundation.awsec2_instance_id
    self.name = foundation.locator
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
    return ( 'set_power', { 'state': self.desired_state, 'instance_id': self.instance_id, 'name': self.name, 'sent': self.sent } )

  def fromSubcontractor( self, data ):
    self.curent_state = data[ 'state' ]
    self.sent = True

  def __getstate__( self ):
    return ( self.instance_id, self.desired_state, self.curent_state, self.sent, self.name )

  def __setstate__( self, state ):
    self.instance_id = state[0]
    self.desired_state = state[1]
    self.curent_state = state[2]
    self.sent = state[3]
    self.name = state[4]


class power_state( ExternalFunction ):
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.instance_id = foundation.awsec2_instance_id
    self.name = foundation.locator
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
    return ( 'power_state', { 'instance_id': self.instance_id, 'name': self.name } )

  def fromSubcontractor( self, data ):
    self.state = data[ 'state' ]

  def __getstate__( self ):
    return ( self.instance_id, self.state, self.name )

  def __setstate__( self, state ):
    self.instance_id = state[0]
    self.state = state[1]
    self.name = state[2]


class set_interface_macs():
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.foundation = foundation

  def __call__( self, interface_list ):
    for interface in interface_list:
      try:
        iface = self.foundation.networkinterface_set.get( name=interface[ 'name' ] )
      except ObjectDoesNotExist:
        raise ParameterError( 'interface_list', 'interface named "{0}" not found'.format( interface[ 'name' ] ) )

      iface.mac = interface[ 'mac' ]

      try:
        iface.full_clean()
      except ValidationError as e:
        raise ParameterError( 'interface_list', 'Error saving interface "{0}": {1}'.format( interface[ 'name' ], e ) )

      iface.save()


class set_ip_addresses():
  def __init__( self, foundation, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.foundation = foundation

  def __call__( self, ip_address_map ):
    for interface, ip_address in ip_address_map.items():
      address_block, address_offset = ipAddress2Native( ip_address )
      try:
        addr = Address.objects.get( networked=self.foundation.structure, interface_name=interface )
      except ObjectDoesNotExist:
        raise ParameterError( 'ip_address_map', 'Address for interface "{0}" does not exist'.format( interface ) )

      addr.offset = address_offset
      addr.address_block = address_block

      try:
        addr.full_clean()
      except ValidationError as e:
        raise ParameterError( 'ip_address_map', 'Error Saving ip Address "{0}": {1}'.format( interface, e ) )

      addr.save()


# plugin exports

TSCRIPT_NAME = 'aws'

TSCRIPT_FUNCTIONS = {
                      'create': create,
                    }

TSCRIPT_VALUES = {
                 }
