This file gives information about the registered voter files provided by the Office of the Minnesota Secretary of State under Minnesota Statutes 201.091.

Data contained in the registered voter file is current as of the time the report is run from the Statewide Voter Registration System, and only includes currently registered voters.

*********************************************************************************************
***The OSS does not offer support for using this data with specific software applications.***
*********************************************************************************************

COMMA-DELIMITED FORMAT

Contents of text files are in a comma-delimited (csv) format, which means that the value for each field is separated by a comma and each field's value is surrounded by quotation marks. These files can be imported into most spreadsheet and database software, and converted into columns by selecting the data and using the "Text to Columns" command. Exact wording may differ, but in general, choose Delimited/Separated (not Fixed Width), Comma as Delimiter/Separator, and Double Quotes as Text Qualifier/Delimiter. Consult your software's documentation for the exact process of converting text to columns.

SEPARATE VOTER AND ELECTION FILES

Detailed voting history text files will come in two separate files. "Voter" files have one record for each active voter. "Election" files have one record for each election each voter has voted in. Note that voters may have resided in a different location when they voted in previous elections.

The VoterID field may be used as a primary key to link these two files. In database terms, joining a voter record to the voter's election history will be a one-to-many join. If joined in a database, queries may be used to filter and extract desired information. Consult your software's documentation for details on filtering and queries.

If you have ordered a statewide file, there will be eight Voter files and eight Election files produced, one for each Congressional District.

MAILING LABEL FILES

Mailing label pdf files are designed to be printed on Avery 5160 (or similar 3 x 10) label sheets. County code, precinct code, and school district are in the upper right corner of each label. On the Registered Voter version, VoterID is in the upper left corner of each label. 

Mailing label text files may be used to create labels using mail merge functionality. Consult your software's documentation for details on performing mail merges.

ABBREVIATIONS

The files include various abbreviations--find explanations listed below.

Districts

CG - Congressional District
CM - County Commissioner District
CNTY - County
HD - Hospital District
JD - Judicial District
LG - Legislative District
MCD - Minor Civil Division ID
PCT - Precinct
PD - Park District
SD - School District (number after dash is board member district)
SS - State Senate District
SW - Soil & Water Conservation District

Voting Methods

A - Voted by Absentee Ballot
M - Voted by Mail (Mail Ballot precinct)
N - Information unavailable 
P - Voted in Person

Election Types

MG - Municipal General Election
MP - Municipal Primary
PNP - Presidential Nomination Primary
SDG - School District Election
SDP - School District Primary
SDSE - School District Special Election
SDSP - School District Special Primary
SE - Special Election
STG - State General Election
STP - State Primary
