from contractor.tscript.runner import ExternalFunction, ParameterError


class ping( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.target = None
    self.count = None
    self.result = None

  @property
  def done( self ):
    return self.result is not None

  @property
  def message( self ):
    if self.result is None:
      return 'Waiting for Ping Results'
    else:
      return 'Ping result "{0}"'.format( self.result )

  @property
  def value( self ):
    return self.result

  def setup( self, parms ):
    try:
      self.target = parms[ 'target' ]
    except KeyError:
      raise ParameterError( 'target', 'required' )

    if self.target is None:
      raise ParameterError( 'target', 'is None' )

    try:
      self.count = int( parms.get( 'count', 5 ) )
    except ( ValueError, TypeError ):
      raise ParameterError( 'count', 'must be an integer' )

  def toSubcontractor( self ):
    return ( 'ping', { 'target': self.target, 'count': self.count } )

  def fromSubcontractor( self, data ):
    self.result = data[ 'result' ]

  def __getstate__( self ):
    return ( self.target, self.count, self.result  )

  def __setstate__( self, state ):
    self.target = state[0]
    self.count = state[1]
    self.result = state[2]


class waitForPort( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.curent_state = None

  @property
  def done( self ):
    return self.curent_state == 'open'

  @property
  def message( self ):
    return 'Port State Curently "{0}"'.format( self.curent_state )

  def setup( self, parms ):
    try:
      self.target = parms[ 'target' ]
    except KeyError:
      raise ParameterError( 'target', 'required' )

    if self.target is None:
      raise ParameterError( 'target', 'is None' )

    try:
      self.port = int( parms[ 'port' ] )
    except ( ValueError, TypeError, KeyError ):
      raise ParameterError( 'count', 'is required and must be an integer' )

  def toSubcontractor( self ):
    return ( 'port_state', { 'target': self.target, 'port': self.port } )

  def fromSubcontractor( self, data ):
    self.curent_state = data[ 'state' ]

  def __getstate__( self ):
    return ( self.target, self.port, self.curent_state  )

  def __setstate__( self, state ):
    self.target = state[0]
    self.port = state[1]
    self.curent_state = state[2]


def _snmpSetup( obj, parms ):
  try:
    obj.host = parms[ 'host' ]
  except KeyError:
    raise ParameterError( 'host', 'required' )

  if obj.host is None:
    raise ParameterError( 'host', 'is None' )

  try:
    obj.protocol = parms[ 'protocol' ]
    if obj.protocol not in ( 'SNMPv1', 'SNMPv2c', 'SNMPv3' ):
      raise ParameterError( 'protocol', 'invalid' )
  except KeyError:
    obj.protocol = 'SNMPv2c'

  creds = {}
  if obj.protocol == 'SNMPv3':
    try:
      creds[ 'user' ] = parms[ 'user' ]
    except KeyError:
      raise ParameterError( 'user', 'required' )

    if creds[ 'user' ] is None:
      raise ParameterError( 'user', 'is None' )

    for name in ( 'auth_key', 'priv_key' ):
      try:
        creds[ name ] = parms[ name ]
      except KeyError:
        pass

  else:
    try:
      creds[ 'community' ] = parms[ 'community' ]
    except KeyError:
      raise ParameterError( 'community', 'required' )

    if creds[ 'community' ] is None:
      raise ParameterError( 'community', 'is None' )

  obj.creds = creds

  try:
    obj.oid = parms[ 'oid' ]
  except KeyError:
    raise ParameterError( 'oid', 'required' )

  if obj.oid is None:
    raise ParameterError( 'oid', 'is None' )


class snmpGet( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.host = None
    self.protocol = None
    self.creds = {}
    self.oid = None
    self.result = None

  @property
  def done( self ):
    return self.result is not None

  @property
  def message( self ):
    if self.result is None:
      return 'Waiting for SNMP Get'
    else:
      return 'SNMP Get Complete'

  @property
  def value( self ):
    return self.result

  def setup( self, parms ):
    _snmpSetup( self, parms )

  def toSubcontractor( self ):
    return ( 'snmp_get', { 'connection': { 'host': self.host, 'protocol': self.protocol, 'creds': self.creds }, 'oid': self.oid } )

  def fromSubcontractor( self, data ):
    self.result = data[ 'value' ]

  def __getstate__( self ):
    return ( self.host, self.protocol, self.creds, self.oid, self.result )

  def __setstate__( self, state ):
    self.host = state[0]
    self.protocol = state[1]
    self.creds = state[2]
    self.oid = state[3]
    self.result = state[4]


class snmpSet( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.host = None
    self.protocol = None
    self.creds = {}
    self.oid = None
    self.new_value = None
    self.complete = None

  @property
  def done( self ):
    return self.complete is True

  @property
  def message( self ):
    if self.complete is not True:
      return 'Waiting for SNMP Get'
    else:
      return 'SNMP Set Complete'

  def setup( self, parms ):
    _snmpSetup( self, parms )

    try:
      self.new_value = parms[ 'value' ]
    except KeyError:
      raise ParameterError( 'value', 'required' )

  def toSubcontractor( self ):
    return ( 'snmp_set', { 'connection': { 'host': self.host, 'protocol': self.protocol, 'creds': self.creds }, 'oid': self.oid, 'value': self.new_value } )

  def fromSubcontractor( self, data ):
    self.complete = data.get( 'done', False )

  def __getstate__( self ):
    return ( self.host, self.protocol, self.creds, self.oid, self.new_value, self.complete )

  def __setstate__( self, state ):
    self.host = state[0]
    self.protocol = state[1]
    self.creds = state[2]
    self.oid = state[3]
    self.new_value = state[4]
    self.complete = state[5]


# plugin exports

TSCRIPT_NAME = 'iputils'

TSCRIPT_FUNCTIONS = {
                      'ping': ping,
                      'wait_for_port': waitForPort,
                      'snmp_get': snmpGet,
                      'snmp_set': snmpSet
                    }

TSCRIPT_VALUES = {
                 }
