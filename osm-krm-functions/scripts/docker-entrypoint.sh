#!/bin/bash
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

# "Debug mode" variable
DEBUG="${DEBUG:-}"
[[ "${DEBUG,,}" == "true" ]] && set -x

# If there is an input stream, dumps it into a temporary file and sets it as INFILE
if [[ -n "${INSTREAM}" ]];
then
    # Save input stream to temporary file
    TMPFILE=$(mktemp /tmp/INSTREAM.XXXXXXXXXX) || exit 1
    echo "${INSTREAM}" > "${TMPFILE}"
    export INFILE="${TMPFILE}"
fi

# Sets default INPUT and OUTPUT
INFILE="${INFILE:-/dev/stdin}"
OUTFILE="${OUTFILE:-/dev/stdout}"

# Loads helper functions and KRM functions
source /app/scripts/library/helper-functions.rc
source /app/scripts/library/krm-functions.rc

# If applicable, loads additional environment variables
if [[ -n "${CUSTOM_ENV}" ]];
then
    set -a
    source <(echo "${CUSTOM_ENV}")
    set +a
fi

# In case INFILE and OUTFILE are the same, it uses a temporary output file
if [[ "${INFILE}" == "${OUTFILE}" ]];
then
    TMPOUTFILE="$(mktemp "/results/OUTFILE.XXXXXXXXXX")" || exit 1
else
    TMPOUTFILE="${OUTFILE}"
fi

#################### EXECUTION ####################
# Debug mode:
if [[ "${DEBUG,,}" == "true" ]];
then
    "$@" < "${INFILE}" | tee "${TMPOUTFILE}"
# Normal mode:
else
    "$@" < "${INFILE}" > "${TMPOUTFILE}"
fi
###################################################

# In case INFILE and OUTFILE are the same, it renames the temporary file over the OUTFILE (i.e., the same as INFILE)
if [[ "${INFILE}" == "${OUTFILE}" ]];
then
    mv -f "${TMPOUTFILE}" "${OUTFILE}"
fi
