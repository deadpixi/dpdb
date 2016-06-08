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
    statement1=SELECT * FROM foo WHERE bar = ${baz}

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

Each section whose name starts with "QUERY" defines a query.
The name of the query is the name of the section with "QUERY " stripped
off the front.

If a "parameters" option is defined in that section, the value of
that option is a space-separated list of argument names.

Each statement in a query is defined by having an arbitrary
number of options whose names start with "statement".
Note that these options are lexically sorted at load time,
so pay careful attention to the names you choose.

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
