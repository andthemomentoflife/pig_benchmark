import argparse
import json
import math

from flask import Flask, Response, request, jsonify
from flask.json import loads
import flask.ext.sqlalchemy
import flask.ext.restless

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

import sldb.api.queries as queries
from sldb.common.models import *

app = flask.Flask(__name__)


def _add_cors_header(response):
    """Add headers to allow cross-site requests"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET'
    response.headers['Access-Control-Allow-Headers'] = (
        'Origin, X-Requested-With, Content-Type, Accept')
    response.headers['Access-Control-Allow-Credentials'] = 'true'

    return response


def _get_paging():
    """Handles paging based on a request's query string"""
    page = request.args.get('page') or 1
    per_page = request.args.get('per_page') or 10
    page = int(page)
    per_page = int(per_page)
    return page, per_page


def _split(ids, delim=','):
    """Helper function to split a string into an integer array"""
    return map(int, ids.split(delim))


def _get_arg(key, json=True):
    req = request.args.get(key)
    if req is None or len(req.strip()) == 0:
        return None
    return loads(req.strip()) if json else req.strip()


@app.route('/api/sequence/<sample_id>/<seq_id>')
def sequence(sample_id, seq_id):
    session = scoped_session(session_factory)()
    seq = jsonify(sequence=queries.get_sequence(session, int(sample_id),
                                                seq_id))
    session.close()
    return seq


@app.route('/api/subjects/', methods=['GET'])
def subjects():
    """Gets a list of all subjects"""
    session = scoped_session(session_factory)()
    subjects = queries.get_all_subjects(session, _get_paging())
    session.close()
    return jsonify(subjects=subjects)


@app.route('/api/subject/<sid>', methods=['GET'])
def subject(sid):
    session = scoped_session(session_factory)()
    subject = queries.get_subject(session, int(sid))
    session.close()
    return jsonify(subject=subject)


@app.route('/api/clones/', methods=['GET'])
def clones():
    """Gets a list of all clones"""
    session = scoped_session(session_factory)()
    clones = queries.get_all_clones(
        session, 
        _get_arg('filter'),
        _get_arg('order_field', False) or 'id',
        _get_arg('order_dir', False) or 'desc',
        _get_paging())
    session.close()
    return jsonify(objects=clones)


@app.route('/api/clone_compare/<uids>', methods=['GET'])
def clone_compare(uids):
    """Compares clones by determining their mutations"""
    session = scoped_session(session_factory)()
    clones_and_samples = []
    for u in uids.split(','):
        clones_and_samples.append(_split(u, '_'))
    clones = queries.compare_clones(session, clones_and_samples)
    session.close()
    return jsonify(clones=clones)


@app.route('/api/clone_overlap/<filter_type>/<samples>', methods=['GET'])
@app.route('/api/subject_clones/<filter_type>/<subject>', methods=['GET'])
def clone_overlap(filter_type, samples=None, subject=None):
    """Gets clonal overlap between samples"""
    samples = _split(samples) if samples is not None else None
    session = scoped_session(session_factory)()
    items = queries.get_clone_overlap(
        session, filter_type, samples, subject, _get_paging())
    session.close()
    return jsonify(items=items)


@app.route('/api/data/clone_overlap/<filter_type>/<samples>', methods=['GET'])
@app.route('/api/data/subject_clones/<filter_type>/<subject>', methods=['GET'])
def download_clone_overlap(filter_type, samples=None, subject=None):
    """Downloads a CSV of the clonal overlap between samples"""
    session = scoped_session(session_factory)()
    sample_ids = _split(samples) if samples is not None else None
    data = queries.get_clone_overlap(session, filter_type, sample_ids, subject)
    session.close()

    def _gen(data):
        yield ','.join([
            'clone_id', 'samples', 'total_sequences', 'unique_sequences',
            'subject', 'v_gene', 'j_gene', 'cdr3_len', 'cdr3_aa', 'cdr3_nt']) + \
            '\n'
        for c in data:
            yield ','.join(map(str, [c['clone']['id'],
                            c['samples'].replace(',', ' '),
                           c['total_sequences'],
                           c['unique_sequences'],
                           '{} ({})'.format(
                               c['clone']['subject']['identifier'],
                               c['clone']['subject']['study']['name']),
                           c['clone']['v_gene'],
                           c['clone']['j_gene'],
                           c['clone']['cdr3_aa'],
                           c['clone']['cdr3_nt']])) + '\n'

    if samples is not None:
        fn = 'overlap_{}_{}.csv'.format(
            filter_type,
            samples.replace(',', '-'))
    else:
        fn = 'subject_{}_{}.csv'.format(
            filter_type,
            subject)
    return Response(_gen(data), headers={
        'Content-Disposition':
        'attachment;filename={}'.format(fn)})


@app.route(
    '/api/data/sequences/<file_type>/<replace_germ>/<cid>/<params>',
    methods=['GET'])
def download_sequences(file_type, replace_germ, cid, params):
    cid = int(cid)
    replace_germ = True if replace_germ == 'true' else False
    fn = '{}-{}'.format(cid, 'replaced' if replace_germ else 'original')

    session = scoped_session(session_factory)()
    sequences = []
    for clone_and_sample in params.split(','):
        clone_id, sample = _split(clone_and_sample, '_')
        if clone_id != cid:
            continue
        fn += '_{}'.format(sample)
        for s in session.query(Sequence)\
            .filter(Sequence.sample_id == sample)\
            .filter(Sequence.clone_id == cid):
            sequences.append({
                'sample_name': s.sample.name,
                'seq_id': s.seq_id,
                'sequence': s.sequence_replaced if replace_germ else s.sequence
            })
    session.close()

    def _gen(sequences):
        for seq in sequences:
            if file_type == 'fasta':
                yield '>{},{}\n{}\n\n'.format(
                    seq['sample_name'],
                    seq['seq_id'],
                    seq['sequence'])

    return Response(_gen(sequences), headers={
        'Content-Disposition':
        'attachment;filename={}.fasta'.format(fn)})


@app.route('/api/v_usage/<filter_type>/<samples>', methods=['GET'])
def v_usage(filter_type, samples):
    """Gets the V usage for samples in a heatmap-formatted array"""
    session = scoped_session(session_factory)()
    data, headers = queries.get_v_usage(session, filter_type, _split(samples))
    session.close()
    x_categories = headers
    y_categories = data.keys()

    array = []
    for j, y in enumerate(y_categories):
        for i, x in enumerate(x_categories):
            usage_for_y = data[y]
            if x in usage_for_y:
                array.append([i, j, usage_for_y[x]])
            else:
                array.append([i, j, 0])

    return jsonify(x_categories=x_categories,
                   y_categories=y_categories,
                   data=array)


@app.route('/api/data/v_usage/<filter_type>/<samples>', methods=['GET'])
def download_v_usage(filter_type, samples):
    """Downloads a CSV of the V usage for samples"""
    session = scoped_session(session_factory)()
    data, headers = queries.get_v_usage(session, filter_type, _split(samples))
    session.close()
    ret = 'sample,' + ','.join(headers) + '\n'
    for sample, dist in data.iteritems():
        row = [sample]
        for gene in headers:
            if gene in dist:
                row.append(dist[gene])
            else:
                row.append(0)
        ret += ','.join(map(str, row)) + '\n'

    return Response(ret, headers={
        'Content-Disposition':
        'attachment;filename=v_usage-{}_{}.csv'.format(
            filter_type,
            samples.replace(',', '-'))})


def init_db(host, user, pw, db):
    """Initializes the database session"""
    engine = create_engine(('mysql://{}:{}@{}/'
                            '{}?charset=utf8&use_unicode=0').format(
                                user, pw, host, db))

    Base.metadata.create_all(engine)
    Base.metadata.bind = engine
    global session_factory
    session_factory = sessionmaker(bind=engine)


def run_rest_service():
    """Runs the rest service based on command line arguments"""
    parser = argparse.ArgumentParser(
        description='Provides a restless interface to the master table '
                    'database')
    parser.add_argument('host', help='mySQL host')
    parser.add_argument('db', help='mySQL database')
    parser.add_argument('user', help='mySQL user')
    parser.add_argument('pw', help='mySQL password')
    parser.add_argument('-p', default=5000, type=int, help='API offer port')
    args = parser.parse_args()

    app.config['SQLALCHEMY_DATABASE_URI'] = (
        'mysql://{}:{}@localhost/'
        '{}?charset=utf8&use_unicode=0').format(args.user, args.pw, args.db)
    db = flask.ext.sqlalchemy.SQLAlchemy(app)

    manager = flask.ext.restless.APIManager(app, flask_sqlalchemy_db=db)

    manager.create_api(Study, methods=['GET'])
    manager.create_api(Sample, methods=['GET'], include_columns=[
                       'id', 'name', 'info', 'study'])
    manager.create_api(SampleStats, methods=['GET'], collection_name='stats',
                       max_results_per_page=10000,
                       results_per_page=10000)
    manager.create_api(CloneFrequency, methods=['GET'],
                       collection_name='clone_freqs',
                       exclude_columns=['sample'])
    init_db(args.host, args.user, args.pw, args.db)

    app.after_request(_add_cors_header)
    app.run(host='0.0.0.0', port=args.p, debug=True, threaded=True)
