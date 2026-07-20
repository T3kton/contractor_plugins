from contractor.tscript.runner import ExternalFunction, ParameterError


class execute( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.host = None
    self.username = None
    self.password = None
    self.command = None
    self.timeout = 300
    self.expected_rc = 0
    self.rc = None

  @property
  def done( self ):
    return self.rc is not None

  @property
  def message( self ):
    if self.rc is not None:
      return 'Execution Returned "{0}"'.format( self.rc )
    else:
      return 'Waiting for Execution Results'

  @property
  def value( self ):
    if self.rc != self.expected_rc:
      return Exception( 'Command returned "{0}", expected "{1}"'.format( self.rc, self.expected_rc ) )
    else:
      return True

  def setup( self, parms ):
    for name in ( 'host', 'command' ):
      try:
        setattr( self, name, parms[ name ] )
      except KeyError:
        raise ParameterError( name, 'required' )

    for name in ( 'username', 'password' ):
      try:
        setattr( self, name, parms[ name ] )
      except KeyError:
        pass

    for name in ( 'timeout', 'expected_rc' ):
      try:
        setattr( self, name, int( parms[ name ] ) )
      except ValueError:
        raise ParameterError( name, 'must be valid integer' )
      except KeyError:
        pass

  def toSubcontractor( self ):
    return ( 'execute', { 'host': self.host, 'username': self.username, 'password': self.password, 'command': self.command, 'timeout': self.timeout } )

  def fromSubcontractor( self, data ):
    self.rc = data[ 'rc' ]

  def __getstate__( self ):
    return ( self.host, self.username, self.password, self.command, self.timeout, self.expected_rc, self.rc )

  def __setstate__( self, state ):
    self.host = state[0]
    self.username = state[1]
    self.password = state[2]
    self.command = state[3]
    self.timeout = state[4]
    self.expected_rc = state[5]
    self.rc = state[6]


class file( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.host = None
    self.username = None
    self.password = None
    self.source = None
    self.destination = None
    self.rc = None

  @property
  def done( self ):
    return self.rc is not None

  @property
  def message( self ):
    if self.rc is not None:
      return 'File Copy Results "{0}"'.format( self.rc )
    else:
      return 'Waiting for File Copy'

  @property
  def value( self ):
    return self.rc

  def setup( self, parms ):
    for name in ( 'host', 'username', 'password', 'source', 'destination' ):
      try:
        setattr( self, name, parms[ name ] )
      except KeyError:
        raise ParameterError( name, 'required' )

  def toSubcontractor( self ):
    return ( 'file', { 'host': self.host, 'username': self.username, 'password': self.password, 'source': self.source, 'destination': self.destination } )

  def fromSubcontractor( self, data ):
    self.rc = data[ 'rc' ]

  def __getstate__( self ):
    return ( self.host, self.username, self.password, self.source, self.destination, self.rc  )

  def __setstate__( self, state ):
    self.host = state[0]
    self.username = state[1]
    self.password = state[2]
    self.source = state[3]
    self.destination = state[4]
    self.rc = state[5]


# plugin exports

TSCRIPT_NAME = 'ssh'

TSCRIPT_FUNCTIONS = {
                      'execute': execute,
                      'file': file,
                    }

TSCRIPT_VALUES = {
                 }
