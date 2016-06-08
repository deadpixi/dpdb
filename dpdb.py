#!/usr/bin/env python

"""
Introduction
============
This module provides a simple wrapper mechanism that abstracts away
differences in various DB-API modules.  It is compatible with both Python
2.7 and Python 3.x.

The Python DB-API specifies a standardized set of mechanisms to access
different database engines.  However, the specification allows for
considerable leeway in how SQL statements and queries are presented to the
user, including different parameter quoting styles.

This module abstracts away those differences and also allows for SQL
statements and queries to be completely isolated from Python code.  It serves
as a very lightweight database abstraction library, and makes it possible
to switch database engines by swapping out a single configuration file.
Unlike many full-fledged ORM systems, it does not impose any structural
requirements on the database itself and in fact encourages programmers to
write arbitrarily complex queries that take advantage of the database's
native ability to manipulate data.

The core of the module is the Database class, which represents a connection
to a database.  Database objects are instantiated with a configuration that
describes how to connect to a database (what module to use and what arguments
to pass to the module's `connect` function), and what queries will be run
on the database.  Configurations are just Python dictionaries (or any other
object that inherits from the `collections.Mapping` abstract base class),
and can be easily read from JSON files or `ConfigParser` objects.  Here is
a simple example configuration that connects to a SQLite in-memory database:

    >>> config = {
    ...     "MODULE": {
    ...         "name": "sqlite3"
    ...     },
    ...     "DATABASE": {
    ...         "database": ":memory:"
    ...     },
    ...     "QUERIES": {
    ...         "create_table": "CREATE TABLE users (name TEXT NOT NULL PRIMARY KEY, password TEXT NOT NULL)",
    ...         "create_user": "INSERT INTO users(name, password) VALUES(${name}, ${password})",
    ...         "list_users": "SELECT * FROM users ORDER BY name ASC",
    ...         "get_password": "SELECT password FROM users WHERE name = ${name}",
    ...         "delete_user": "DELETE FROM users WHERE name = ${name}"
    ...     }
    ... }

We can create a database using this configuration and create a test
table using the "create_table" query that we defined (in a real world
implementation, the database would probably have already been populated,
but this serves well for an example):

    >>> db = Database(config)
    >>> result = db.create_table()

Note how the queries we've defined become methods on the Database object
we created.

We can call methods on the database object to execute queries, passing
parameters in as necessary.  The parameters are automatically converted to
the module's appropriate paramter quoting mechanism:

    >>> result = db.create_user(name="bruce", password="iamthenight")
    >>> result = db.create_user(name="arthur", password="glublub")

The arguments passed to the query are safely substituted into the queries
defined in the configuration.  Queries return results as lists of rows
passed through a row factory function; by default this turns each row into
a dictionary mapping column names to values:

    >>> db.list_users() == [{"name": "arthur", "password": "glublub"}, {"name": "bruce", "password": "iamthenight"}]
    True

A different factory function can be specified at instantiation time.
It takes two arguments: a DB-API standard cursor object and a row, and can
return any value.  For example, here is the default row factory function:

    >>> def row_factory(cursor, row):
    ...     return dict((name[0], value) for name, value in zip(cursor.description, row))

    >>> db2 = Database(config, row_factory)
    >>> result = db2.create_table()
    >>> result = db2.create_user(name="dick", password="batmanrules")
    >>> db2.list_users() == [{"name": "dick", "password": "batmanrules"}]
    True

Connection and Transaction Contexts
===================================
The Database class also acts as a context manager:

    >>> with Database(config) as db:
    ...     result = db.create_table()
    ...     result = db.create_user(name="hal", password="brightestday")
    ...     result = db.list_users()

The Transaction class also provides a context manager that implements
transactions:

    >>> db = Database(config)
    >>> result = db.create_table()
    >>> try:
    ...     with Transaction(db):
    ...         result = db.create_user(name="hal", password="brightestday")
    ...         result = db.create_user(name="hal", password="darkestnight")
    ... except Exception:
    ...     print("transaction failed")
    transaction failed

And note that because the failure happened within a transaction, nothing
was added to the database:

    >>> db.list_users()
    []

This mechanism has the nice benefit that transactions can include non-database
related statements within the context that will cause an automatic transaction
rollback should they fail.

Unsafe Substitutions
====================
The "QUERIES" section of the database configuration allows parameterization
using `string.Template` syntax.  These substitutions are automatically
converted to the module's native substitution format (`qmark`, `named`, etc).
These substitutions can appear in arbitrarily complex queries:

    >>> config["QUERIES"]["update_password"] = "UPDATE users SET password = COALESCE(${password}, password) WHERE name = ${name}"
    >>> with Database(config) as db:
    ...     result = db.create_table()
    ...     result = db.create_user(name="clark", password="greatcaesarsghost")
    ...     result = db.update_password(name="clark", password="visitbeautifulkandor")
    ...     db.list_users() == [{"name": "clark", "password": "visitbeautifulkandor"}]
    True

However, many database engines only allow certain portions of queries to be
parameterized using parameter substitution.  Often, "structural" components
in a query (the names of tables, columns used for sorting, sort order,
limits) cannot be substituted using the module's substitution mechanism.
For these sorts of situations, unsafe substitution can be used.  Note that
the name means what it says: using this form of substitution can result in
SQL injection attacks, so use them wisely!

Unsafe substitutions are indicated by using normal Python string interpolation
syntax.  For example:

    >>> config["QUERIES"]["list_users"] = "SELECT * FROM users ORDER BY name %(order)s"
    >>> db = Database(config)
    >>> result = db.create_table()
    >>> result = db.create_user(name="ralghul", password="lazarus")
    >>> result = db.create_user(name="ocobblepot", password="wahwahwah")
    >>> db.list_users(order="DESC") == [{"name": "ralghul", "password": "lazarus"}, {"name": "ocobblepot", "password": "wahwahwah"}]
    True
    >>> db.list_users(order="ASC") == [{"name": "ocobblepot", "password": "wahwahwah"}, {"name": "ralghul", "password": "lazarus"}]
    True
    >>> db.close()

Unsafe substitutions can add new safe substitutions:

    >>> config["QUERIES"]["get_user_with_predicate"] =  "SELECT * FROM users WHERE %(predicate)s"
    >>> db = Database(config)
    >>> result = db.create_table()
    >>> result = db.create_user(name="vfries", password="socold")
    >>> db.get_user_with_predicate(predicate="name LIKE ${pattern}", pattern="v%") == [{"name": "vfries", "password": "socold"}]
    True

Runtime Configuration
=====================
For simplicity of use, a handle and a module can be passed directly to the
Database init method:

    >>> import sqlite3
    >>> config2 = {
    ...     "QUERIES": {
    ...         "create_table": "CREATE TABLE users (name TEXT NOT NULL PRIMARY KEY, password TEXT NOT NULL)",
    ...         "create_user": "INSERT INTO users(name, password) VALUES(${name}, ${password})",
    ...         "list_users": "SELECT * FROM users ORDER BY name ASC",
    ...         "get_password": "SELECT password FROM users WHERE name = ${name}",
    ...         "delete_user": "DELETE FROM users WHERE name = ${name}"
    ...     }
    ... }
    >>> handle = sqlite3.connect(":memory:")
    >>> db = Database(config2, handle=handle, module=sqlite3)
    >>> result = db.create_table()
    >>> result = db.create_user(name="jjonzz", password="oleo")
    >>> db.list_users(order="DESC") == [{"name": "jjonzz", "password": "oleo"}]
    True
    >>> handle.close()

Mapping Positional Names and Custom Return Values
=================================================
Queries can also use positional names:

    >>> config3 = {
    ...     "QUERIES": {
    ...         "create_table": "CREATE TABLE users (name TEXT NOT NULL PRIMARY KEY, password TEXT NOT NULL)",
    ...         "create_user": "INSERT INTO users(name, password) VALUES(${_0}, ${_1})",
    ...         "list_users": "SELECT * FROM users ORDER BY name ASC"
    ...     }
    ... }
    >>> handle2 = sqlite3.connect(":memory:")
    >>> db = Database(config3, handle=handle2, module=sqlite3)
    >>> result = db.create_table()
    >>> result = db.create_user("vstone", "beepboop")
    >>> db.list_users(order="DESC") == [{"name": "vstone", "password": "beepboop"}]
    True
    >>> handle2.close()

If queries are going to be called often using purely positional arguments,
they can be named:

    >>> config4 = {
    ...     "QUERIES": {
    ...         "create_table": "CREATE TABLE users (name TEXT NOT NULL PRIMARY KEY, password TEXT NOT NULL)",
    ...         "create_user": {
    ...             "query": "INSERT INTO users(name, password) VALUES(${username}, ${password})",
    ...             "parameters": ["username", "password"]
    ...         },
    ...         "list_users": "SELECT * FROM users ORDER BY name ASC"
    ...     }
    ... }
    >>> handle3 = sqlite3.connect(":memory:")
    >>> db = Database(config4, handle=handle3, module=sqlite3)
    >>> result = db.create_table()
    >>> result = db.create_user("vstone", "beepboop")
    >>> db.list_users(order="DESC") == [{"name": "vstone", "password": "beepboop"}]
    True

Adding Additional Queries at Runtime
====================================
New queries can be added at runtime:

    >>> db.add_query("uppercase_passwords", "UPDATE users SET password = UPPER(password)")
    >>> result = db.uppercase_passwords()
    >>> db.list_users(order="DESC") == [{"name": "vstone", "password": "BEEPBOOP"}]
    True

The positional-to-name mapping can be provided as an optional third
argument:

    >>> db.add_query("lowercase_password_for_user", "UPDATE users SET password = LOWER(password) WHERE name = ${name}", ["name"])
    >>> result = db.lowercase_password_for_user("vstone")
    >>> db.list_users(order="DESC") == [{"name": "vstone", "password": "beepboop"}]
    True

Multi-Statement Queries
=======================
A single query can contain multiple statements.
These statements will be executed in order and within a transaction.
The result of the last statement is the result of the query:

    >>> db.add_query("create_user_returning_id", [
    ...     "INSERT INTO users(name, password) VALUES(${username}, ${password})",
    ...     "SELECT last_insert_rowid() AS id"
    ... ], ["username", "password"])
    >>> result = db.create_user_returning_id("oqueen", "thequiver")
    >>> "id" in result[0] and isinstance(result[0]["id"], int)
    True

Extended ConfigParser Format
============================
Python 3.x ConfigParser objects can be used "naturally", since they conform
to the Mapping protocol. Such files look like this::

    [MODULE]
    name=sqlite3

    [DATABASE]
    database=:memory:

    [QUERIES]
    example1=SELECT * FROM foo WHERE bar = ${baz}

However, this "natural" mapping doesn't specification of multi-statement
queries or named positional arguments.

(Note that JSON files are also "natural" to use, but without line breaks in
strings it's hard to make large queries readable.)

As a convenience to the user, the Database class supports two static
constructors: `from_config` and `from_config_file`. Addtionally, two
instance methods are defined: `load_queries_from_config` and
`load_queries_from_config_file`.

These constructors read a specially-formed ConfigParser file format that
supports all of this module's special features. Note that it is in no way
required to use this format for configuration: JSON files, regular ConfigParser
objects (in Python 3.x), Python dictionaries, or any other Mapping can be
used. This special format is just a convenience, especially for Python 2.x
users.

The format looks like this:

    >>> config5 = '''
    ... [MODULE]
    ... name = sqlite3
    ...
    ... [DATABASE]
    ... database = :memory:
    ...
    ... [QUERY create_table]
    ... statement1 = CREATE TABLE users (
    ...         name     TEXT NOT NULL PRIMARY KEY,
    ...         password TEXT NOT NULL
    ...      )
    ...
    ... [QUERY create_user_returning_id]
    ... parameters  = name password
    ... statement1  = INSERT INTO users(name, password) VALUES(${name}, ${password})
    ... statement2  = SELECT last_insert_rowid() AS id
    ... '''

This configuration can be used like this:

    >>> db = Database.from_config(config5)
    >>> result = db.create_table()
    >>> result = db.create_user_returning_id("dprince", "greathera")
    >>> "id" in result[0] and isinstance(result[0]["id"], int)
    True

Testing This Module
===================
This module has embedded doctests that are run with the module is invoked
from the command line.  Simply run the module directly to run the tests.

Contact Information and Licensing
=================================
This module was written by Rob King (jking@deadpixi.com).

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""


__all__ = ["Database", "Transaction"]
__author__ = "Rob King"
__copyright__ = "Copyright (C) 2015 Rob King"
__license__ = "LGPL"
__version__ = "$Id$"
__email__ = "jking@deadpixi.com"
__status__ = "Alpha"

import collections
import re
import string

try:
    import importlib
    import_module = importlib.import_module

except ImportError:
    def import_module(name):
        return __import__(name)

try:
    from collections import UserDict

except ImportError:
    from UserDict import UserDict

try:
    from ConfigParser import RawConfigParser

except ImportError:
    from configparser import RawConfigParser

try:
    from StringIO import StringIO

except ImportError:
    from io import StringIO

if 'unicode' not in dir(__builtins__):
    unicode = str # for Python 3

def is_string(x):
    return isinstance(x, str) or isinstance(x, unicode)

class Query:
    def __init__(self, queries, database, parameters):
        self.queries = queries
        self.database = database
        self.parameters = parameters

    def __call__(self, *args, **kwargs):
        results = []
        for query in self.queries:
            mapping = self.database.mapping(kwargs)
            mapping.update(("_" + str(i), v) for i, v in enumerate(args))
            mapping.update((k, v) for k, v in zip(self.parameters, args))

            query = string.Template(query % kwargs).substitute(mapping)
            self.database.cursor.execute(query, mapping.get_parameters())

            try:
                results = self.database.cursor.fetchall()
                results = [self.database.row_factory(self.database.cursor, x) for x in results]

            except self.database.module.Error:
                # IMHO, this is a poor design decision on the DB-API's part.
                # Calling fetchall for a query with no results throws this
                # error rather than returning None.
                results = []
                continue

        return results

class Mapping(UserDict):
    def get_parameters(self):
        return self.params

class QmarkMapping(Mapping):
    def __init__(self, mapping):
        UserDict.__init__(self, mapping)
        self.params = []

    def __getitem__(self, item):
        self.params.append(self.data[item])
        return '?'

class NumericMapping(Mapping):
    def __init__(self, mapping):
        UserDict.__init__(self, mapping)
        self.count = 1
        self.params = []

    def __getitem__(self, item):
        self.count += 1
        self.params.append(self.data[item])
        return ':%d' % (self.count - 1)

class NamedMapping(Mapping):
    def __init__(self, mapping):
        UserDict.__init__(self, mapping)
        self.params = {}

    def __getitem__(self, item):
        self.params[item] = self.data[item]
        return ':%s' % item

class FormatMapping(QmarkMapping):
    def __getitem__(self, item):
        self.params.append(self.data[item])
        return '%s'

class PyformatMapping(NamedMapping):
    def __getitem__(self, item):
        self.params[item] = self.data[item]
        return '%%(%s)s' % item

def default_row_factory(cursor, row):
    return dict((n[0], v) for n, v in zip(cursor.description, row))

def dict_of_config(parser):
    config = {}
    for section in parser.sections():
        config[section] = dict((k, v) for k, v in parser.items(section))
    if "QUERIES" not in config:
        config["QUERIES"] = {}

    return config

class Database:
    """
    A database connection.
    """

    @classmethod
    def from_config_file(self, config_file, row_factory=default_row_factory, handle=None, module=None, **parameters):
        with open(config_file, "r") as fp:
            return self.from_config(fp.read(), row_factory, handle, module, **parameters)

    @classmethod
    def from_config(self, config, row_factory=default_row_factory, handle=None, module=None, **parameters):
        s = StringIO(config)
        parser = RawConfigParser()
        parser.readfp(s)

        db = Database(dict_of_config(parser), row_factory, handle, module, **parameters)
        db.load_queries_from_config(config)
        return db

    def load_queries_from_config_file(self, config_file):
        with open(config_file, "r") as fp:
            return self.load_queries_from_config(fp.read())

    def load_queries_from_config(self, config):
        s = StringIO(config)
        parser = RawConfigParser()
        parser.readfp(s)

        config = dict_of_config(parser)

        for section, contents in config.items():
            if section.startswith("QUERY"):
                args = None
                if "parameters" in contents:
                    args = contents["parameters"].split()

                statements = [s[1] for s in sorted(contents.items()) if s[0].startswith("statement")]
                self.add_query(section[len("QUERY "):], statements, args)

    def __init__(self, config, row_factory=default_row_factory, handle=None, module=None, **parameters):
        if not isinstance(config, collections.Mapping):
            raise TypeError("config must be a mapping")

        if handle is None:
            if "MODULE" not in config.keys() or "DATABASE" not in config.keys():
                raise ValueError("missing section in configuration")

            if "name" not in config["MODULE"] or not is_string(config["MODULE"]["name"]):
                raise ValueError("invalid MODULE configuration section; no module name specified")

        if not all(isinstance(x, collections.Mapping) for x in config.values()):
            raise ValueError("invalid section in configuration")

        self.config = config
        self.module = module
        if self.module is None:
            self.module = import_module(config["MODULE"]["name"])

        if getattr(self.module, "apilevel", None) != "2.0":
            raise ValueError("module does not indicate support for Python DB-API 2.0")

        param_mappings = {
            "qmark": QmarkMapping,
            "numeric": NumericMapping,
            "named": NamedMapping,
            "format": FormatMapping,
            "pyformat": PyformatMapping
        }

        if self.module.paramstyle not in param_mappings:
            raise ValueError("module has unsupported paramstyle '%s'" % self.module.paramstyle)
        self.mapping = param_mappings[self.module.paramstyle]

        if handle:
            self.db = handle

        else:
            self.db = self.module.connect(**dict((str(k), (v.format(**parameters) if is_string(v) else v)) for k, v in config["DATABASE"].items()))

        self.queries = {}
        for name, value in config["QUERIES"].items():
            if isinstance(value, collections.Mapping):
                if "query" not in value or "parameters" not in value:
                    raise ValueError("invalid query specification for '%s'" % name)

                self.add_query(name, value["query"], value["parameters"])

            else:
                self.add_query(name, value)

        self.cursor = self.db.cursor()
        self.row_factory = row_factory
        self._transaction = 0

    def _enter_transaction(self):
        self._transaction += 1

    def _exit_transaction(self, rollback=False):
        assert self._transaction > 0
        self._transaction = max(0, self._transaction - 1)
    
        if rollback:
            if hasattr(self.db, "rollback"):
                self.db.rollback()

        elif self._transaction <= 0:
            self.db.commit()

    def __getattr__(self, attr):
        if attr not in self.queries:
            raise AttributeError("unknown query '%s'" % attr)
        return self.queries[attr]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            if hasattr(self.db, "rollback"):
                self.db.rollback()

        else:
            self.db.commit()

        self.db.close()

    def add_query(self, name, statements, parameters=None):
        query = None
        parameters = parameters or []

        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("invalid query name '%s'" % name)

        if is_string(statements):
            statements = [statements]

        if not isinstance(statements, collections.Sequence) or not all(map(is_string, statements)):
            raise TypeError("invalid query specification for '%s'" % name)

        self.queries[name] = Query(statements, self, parameters)

    def commit(self):
        assert self._transaction == 0
        self.db.commit()

    def rollback(self):
        assert self._transaction == 0
        self.db.rollback()

    def close(self):
        self.db.close()

class Transaction:
    """
    A context handler covering a transaction on a database over multiple statements.
    """

    def __init__(self, db):
        self._db = db

    def __enter__(self):
        self._db._enter_transaction()
        return self

    def __exit__(self, exc_type, exec_value, traceback):
        self._db._exit_transaction(exc_type is not None)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
