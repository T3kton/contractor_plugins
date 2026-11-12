import json

from contractor.tscript.runner import ExternalFunction, ParameterError
from contractor.lib.config import getConfig


# command_list = [ ( set/delete/comment, [path] ) ]

def _interface( attribute_list, config ):
  interface_type = attribute_list.pop( 0 )
  if interface_type != 'ethernet':
    raise ValueError( 'Unknown interface type "{0}"'.format( interface_type ) )

  interface_name = attribute_list.pop( 0 )

  interface_map = config[ '_interface_map' ]

  try:
    interface = interface_map[ interface_name ]
  except KeyError:
    raise ValueError( 'Unknown interface "{0}"'.format( interface_name ) )

  interface_name = interface[ 'name' ]

  address_list = interface[ 'address_list' ]

  if not attribute_list:  # ie: no VIF
    return [ ( 'set', [ 'interfaces', interface_name, 'address', '{0}/{1}'.format( address_list[0][ 'address' ], address_list[0][ 'prefix' ] ) ] ) ]

  vif = attribute_list.pop( 0 )
  # alias_index
  if attribute_list:
    raise ValueError( 'Unknown interface format' )

  address_list = interface.address_list

  for address in address_list:
    if address[ 'alias_index' ] == vif:
      return [ ( 'set', [ 'interfaces', interface_name, 'vif', address[ 'alias_index' ], 'address', '{0}/{1}'.format( address[ 'address' ], address[ 'prefix' ] ) ] ) ]

  raise ValueError( 'Unknown vif/alias_index "{0}"'.format( vif ) )


def _dhcp_relay( foundation, config ):
  result = []
  result.append( ( 'set', [ 'service', 'dhcp-relay', 'server', config[ 'vyos_dhcp_relay_server' ] ] ) )
  for interface in foundation.interface_list:
      result.append( ( 'set', [ 'service', 'dhcp-relay', 'interface', interface.name ] ) )

  param_map = {}
  param_map[ 'server' ] = config[ 'vyos_dhcp_relay_server' ]
  param_map[ 'interface_list' ] = '  \n'.join( [ 'interface {0}'.format( i.name ) for i in foundation.interface_list ] )

  return result


def _buildCommandList( attribute, foundation, structure ):
  config = getConfig( structure )

  if attribute == 'dhcp_relay':
    return _dhcp_relay( foundation, config )

  attribute_list = attribute.split( ':' )
  category = attribute_list.pop( 0 )

  if category == 'interface':
    return _interface( attribute_list, config )

  raise ValueError( 'Unknown attribute "{0}"'.format( attribute ) )


class apply( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.host = None
    self.auth_key = None
    self.command_list = None
    self.executed = False
    self.error = None

  @property
  def done( self ):
    return self.executed

  @property
  def message( self ):
    if self.executed:
      return 'Configuration Applied'
    else:
      return 'Waiting for Configuration'

  @property
  def value( self ):
    if self.error is not None:
      return Exception( 'Error appling config: "{0}"'.format( self.error ) )
    else:
      return True

  def setup( self, parms ):
    try:
      foundation = self.getScriptValue( 'foundation', 'foundation' )
    except ValueError as e:
      raise ParameterError( '<internal>', 'Unable to get Foundation: {0}'.format( e ) )

    structure = foundation.structure

    try:
      attribute = parms[ 'attribute' ]
    except KeyError:
      raise ParameterError( 'attribute', 'required' )

    try:
      auth_key = parms[ 'auth_key' ]
    except KeyError:
      raise ParameterError( 'auth_key', 'required' )

    self.command_list = _buildCommandList( attribute, foundation, structure )
    self.host = structure.primary_ip.ip_address
    self.auth_key = auth_key

  def toSubcontractor( self ):
    return ( 'apply', { 'host': self.host, 'auth_key': self.auth_key, 'command_list': json.dumps( self.command_list ) } )

  def fromSubcontractor( self, data ):
    self.error = data[ 'error' ]
    self.executed = True

  def __getstate__( self ):
    return ( self.host, self.auth_key, self.command_list, self.executed, self.error )

  def __setstate__( self, state ):
    self.host = state[0]
    self.auth_key = state[1]
    self.command_list = state[2]
    self.executed = state[3]
    self.error = state[4]


# plugin exports

TSCRIPT_NAME = 'vyos'

TSCRIPT_FUNCTIONS = {
                      'apply': apply,
                    }

TSCRIPT_VALUES = {
                 }


"""
usage:
the config should include:

vyos_dhcp_relay_server


then to apply:

VyOS.apply( attribute=<attribute name> )


attributes:
  dhcp_relay
  interface:ethernet:<iface name> (will use alias_index == None)
  interface:ethernet:<iface name>:<vif id# (alias_index)>
"""
