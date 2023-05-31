#!/usr/bin/env python3
import argparse
import cgi
import socketserver
from http.server import HTTPServer, SimpleHTTPRequestHandler
import logging, logging.handlers
import json
from urllib.parse import urlparse, parse_qs, unquote
from webapi import MongoDocAnn, PostgresDocAnn, load_json_data
import hashlib
import re
import sys

CONST_VIS_PREFIX = '/vis/'
CONST_API_PREFIX = '/api/'
_api_mapper = None


class APIMapper(object):
    def __init__(self, doc_ann_inst):
        self._inst = doc_ann_inst
        self._passphrase = None

    def set_passphrase(self, pp):
        # store the SHA-256 hash of the passphrase
        pp_sha256 = hashlib.sha256(pp.encode())
        self._passphrase = pp_sha256.hexdigest()

    def validate_passphrase(self, pp):
        # expect the client to pass th SHA-256 hash of the passphrase
        if self._passphrase is None:
            return True
        return self._passphrase == pp

    def map(self, api_call, passphrase=None, queryDict=None, post_data=None):
        """ api_call is the path part of the URL so contains the function name and parameters,
        queryDict is the j= part of the query string in the URL decoded from JSON.
        """
        m = re.search('/api/([^/]{1,255})/', api_call)
        if m:
            func = m.group(1)
            logging.debug('APIMapper::map func = %s' % func)
            if func not in ['check_phrase', 'need_passphrase'] and not self.validate_passphrase(passphrase):
                raise Exception('passphrase needed but not provided or not valid')
            if func == 'docs':
                return self._inst.get_doc_list()
            elif func == 'need_passphrase':
                return self._passphrase is not None
            elif func == 'put_trained_docs':
                return self._inst.put_trained_docs(post_data)
            elif func == 'mappings':
                return self._inst.get_available_mappings()
            elif func in ['doc_content', 'doc_ann', 'doc_detail', 'check_phrase', 'search_docs', 'search_anns',
                    'get_training_docs']:
                m2 = re.search('/api/([^/]{1,255})/([^/]{1,255})/', api_call)
                if m2:
                    if func == 'doc_content':
                        return self._inst.get_doc_content(m2.group(2))
                    elif func == 'doc_ann':
                        logging.debug('getting', m2.group(2))
                        return self._inst.get_doc_ann(m2.group(2))
                    elif func == 'check_phrase':
                        return self._passphrase == m2.group(2)
                    elif func == 'get_training_docs':
                        return self._inst.get_training_docs(m2.group(2))
                    elif func == 'search_docs':
                        return self._inst.search_docs(unquote(m2.group(2)), queryDict=queryDict)
                    elif func == 'search_anns':
                        return self._inst.search_anns(unquote(m2.group(2)), queryDict=queryDict)
                    else: # doc_detail
                        return {"anns": self._inst.get_doc_ann(m2.group(2)),
                                "content": self._inst.get_doc_content(m2.group(2))}
                raise Exception('doc id not found in [%s]' % api_call)
            elif func in ['doc_content_mapping', 'search_anns_by_mapping']:
                m3 = re.search('/api/([^/]{1,255})/([^/]{1,255})/([^/]{1,255})/', api_call)
                if func == 'search_anns_by_mapping':
                    return self._inst.search_anns(unquote(m3.group(2)), map_name=unquote(m3.group(3)))
                else:
                    return {"content": self._inst.get_doc_content(m3.group(2)),
                            "anns": self._inst.get_doc_ann_by_mapping(m3.group(2), unquote(m3.group(3)))}
        raise Exception('path [%s] not valid (needs to be /api/verb/param/)' % api_call)

    @staticmethod
    def get_mapper():
        global _api_mapper
        if _api_mapper is not None:
            return _api_mapper
        else:
            settings = load_json_data('./conf/settings.json')
            if 'databaseBackend' in settings:
                if settings['databaseBackend'] == 'mongoDB':
                    doc_ann_inst = MongoDocAnn(settings['mongoDB'])
                if settings['databaseBackend'] == 'postgreSQL':
                    doc_ann_inst = PostgresDocAnn(settings['postgreSQL'])
            else:
                doc_ann_inst = PostgresDocAnn(settings['postgreSQL'])
            doc_ann_inst.load_mappings(settings['mappings'])
            if 'mappings_dir' in settings:
                doc_ann_inst.load_mappings_dir(settings['mappings_dir'])
            if 'transaction_dir' in settings:
                doc_ann_inst.set_transaction_dir(settings['transaction_dir'])
            if 'training_dir' in settings:
                doc_ann_inst.set_training_dir(settings['training_dir'])
            _api_mapper = APIMapper(doc_ann_inst)
            if 'passphrase' in settings:
                _api_mapper.set_passphrase(settings['passphrase'])
        return _api_mapper


class S(SimpleHTTPRequestHandler):

    def _send_cors_headers(self):
        """ Sets headers required for CORS """
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "x-api-key,Content-Type")

    def _set_headers(self, type='html'):
        self.send_response(200)
        self._send_cors_headers()
        if type == 'html':
            self.send_header("Content-type", "text/html")
        elif type == 'json':
            self.send_header("Content-type", "application/json")
        self.end_headers()

    def _html(self, message):
        """This just generates an HTML document that includes `message`
        in the body. Override, or re-write this do do more interesting stuff.
        """
        content = f"<html><body><h1>{message}</h1></body></html>"
        return content.encode("utf8")  # NOTE: must return a bytes object!

    def output_json(self, message):
        self._set_headers(type='json')
        self.wfile.write(json.dumps(message).encode("utf8"))

    def output_jsonp(self, message, callback_func):
        if callback_func is None:
            self.output_json(message)
            return
        self._set_headers(type='json')
        s_response = '%s(%s)' % (callback_func, json.dumps(message))
        self.wfile.write(s_response.encode("utf8"))

    def handle_request(self, post_data = None):
            callback = None
            try:
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query) # QUERY_STRING
                qs_j = json.loads(qs.get('j', ['{}'])[0]) # value of j=JSON in QUERY_STRING
                callback = qs['callback'][0] if 'callback' in qs else None
                passphrase=qs['passphrase'][0] if 'passphrase' in qs else None
                if post_data and 'content' in post_data:
                    try:
                        qs_j = json.loads(post_data['content'])
                        callback = qs_j.get('callback', None)
                        passphrase = qs_j.get('passphrase', None)
                    except:
                        pass
                logging.debug('PATH = %s' % self.path)
                logging.debug('POST = %s' % post_data)
                logging.debug('QS = %s' % qs)
                self.output_jsonp(APIMapper.get_mapper().map(self.path,
                        passphrase=passphrase,
                        queryDict=qs_j if qs_j else None,
                        post_data=post_data),
                    callback)
            except Exception as err:
                logging.error(err)
                import traceback
                logging.error(traceback.format_exc())
                self.output_jsonp({"success":False, "message":str(err)}, callback)
                # self._set_headers()
                # self.wfile.write(self._html('[ERROR] %s' % err))

    def do_GET(self):
        logging.debug("REQUEST %s HTTP GET: %s" % (self.client_address[0], self.requestline))
        logging.info('request [%s]' % self.path)
        if self.path.startswith(CONST_VIS_PREFIX):
            super().do_GET()
        elif self.path.startswith(CONST_API_PREFIX):
            self.handle_request()
        else:
            self._set_headers()
            self.wfile.write(self._html("Unsupported operation: %s" % self.path))

    def do_HEAD(self):
        logging.debug("REQUEST %s HTTP HEAD: %s" % (self.client_address[0], self.requestline))
        self._set_headers()

    def do_POST(self):
        logging.debug("REQUEST %s HTTP POST: %s" % (self.client_address[0], self.requestline))
        if self.path.startswith(CONST_API_PREFIX):
            content_length = int(self.headers['Content-Length'])
            ctype, pdict = cgi.parse_header(self.headers['Content-Type'])
            #pdict['boundary'] = bytes(pdict['boundary'], "utf-8")
            #pdict['CONTENT-LENGTH'] = int(self.headers['Content-Length'])
            if ctype == 'multipart/form-data':
                form = cgi.FieldStorage( fp=self.rfile, headers=self.headers,
                    environ={'REQUEST_METHOD':'POST', 'CONTENT_TYPE':self.headers['Content-Type'], })
                if isinstance(form["file"], list):
                    for record in form["file"]:
                        # XXX only keeps the last of multiple files
                        logging.debug('POSTED FILES %s' % record.filename)
                        post_data = { 'filename': record.filename,
                            'content': record.file.read() }
                else:
                    logging.debug('POSTED SINGLE FILE %s' % form["file"].filename)
                    post_data = { 'filename': form["file"].filename,
                        'content':form["file"].file.read() }
                logging.debug('POSTED FILES OK')
            else:
                post_data = { 'content': self.rfile.read(content_length) }

            self.handle_request(post_data = post_data)
        else:
            self._set_headers()
            self.wfile.write(self._html("Unsupported operation: HTTP POST"))

    def do_PUT(self):
        logging.debug("REQUEST %s HTTP PUT: %s" % (self.client_address[0], self.requestline))
        # Doesn't do anything with posted data
        self._set_headers()
        self.wfile.write(self._html("Unsupported operation: HTTP PUT"))

    def do_PATCH(self):
        logging.debug("REQUEST %s HTTP PATCH: %s" % (self.client_address[0], self.requestline))
        # Doesn't do anything with posted data
        self._set_headers()
        self.wfile.write(self._html("Unsupported operation: HTTP PATCH"))


def run(server_class=HTTPServer, addr="", port=8000):
    logging.info(f"Starting httpd server on {addr}:{port}")
    server_address = (addr, port)
    httpd = server_class(server_address, S)
    httpd.serve_forever()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Run a simple HTTP server")
    parser.add_argument("-d", "--debug", help="Output log to console too", action='store_true')
    parser.add_argument(
        "-l",
        "--listen",
        default="",
        help="Specify the IP address on which the server listens",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8000,
        help="Specify the port on which the server listens",
    )
    args = parser.parse_args()

    file_handler = logging.handlers.RotatingFileHandler(filename='webserver.log',
        maxBytes = 64*1024*1024, backupCount=9)
    stdout_handler = logging.StreamHandler(sys.stdout)
    handlers = [file_handler]
    if args.debug:
        handlers.append(stdout_handler)
    logging.basicConfig(level=logging.DEBUG, handlers=handlers,
        format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s')

    # create a subclass of HTTPServer which forks a new process for each request
    # so that long-running queries can be handled in parallel
    class forking_server(socketserver.ForkingMixIn, HTTPServer):
        pass
    run(server_class=forking_server, addr=args.listen, port=args.port)
