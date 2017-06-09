from __future__ import print_function

import logging
import random

import networkx as nx
import numpy as np

from gensim.models import Word2Vec


class Graph:

    def __init__(self, nx_G, is_directed, p, q, **kwargs):
        self.G = nx_G
        self.is_directed = is_directed
        self.p = p
        self.q = q

        self.alias_nodes = None
        self.alias_edges = None

    def node2vec_walk(self, walk_length, start_node):
        """
        Simulate a random walk starting from start node.
        """
        G = self.G
        alias_nodes = self.alias_nodes
        alias_edges = self.alias_edges

        walk = [start_node]

        while len(walk) < walk_length:
            cur = walk[-1]
            cur_nbrs = sorted(G.neighbors(cur))
            if len(cur_nbrs) > 0:
                if len(walk) == 1:
                    walk.append(cur_nbrs[alias_draw(alias_nodes[cur][0],
                                                    alias_nodes[cur][1])])
                else:
                    prv = walk[-2]
                    nxt = cur_nbrs[alias_draw(alias_edges[(prv, cur)][0],
                                              alias_edges[(prv, cur)][1])]
                    walk.append(nxt)
            else:
                break

        return walk

    def get_alias_edge(self, src, dst):
        """
        Get the alias edge setup lists for a given edge.
        """
        G = self.G
        p = self.p
        q = self.q

        unnormalized_probs = []
        for dst_nbr in sorted(G.neighbors(dst)):
            if dst_nbr == src:
                unnormalized_probs.append(G[dst][dst_nbr]['weight']/p)
            elif G.has_edge(dst_nbr, src):
                unnormalized_probs.append(G[dst][dst_nbr]['weight'])
            else:
                unnormalized_probs.append(G[dst][dst_nbr]['weight']/q)
        norm_const = sum(unnormalized_probs)
        normalized_probs = \
            [float(u_prob)/norm_const for u_prob in unnormalized_probs]

        return alias_setup(normalized_probs)

    def preprocess_transition_probs(self):
        """
        Preprocessing of transition probabilities for guiding the random walks.
        """
        G = self.G
        is_directed = self.is_directed

        alias_nodes = {}
        for node in G.nodes():
            unnormalized_probs = [
                G[node][nbr]['weight'] for nbr in sorted(G.neighbors(node))
            ]
            norm_const = sum(unnormalized_probs)
            normalized_probs = \
                [float(u_prob)/norm_const for u_prob in unnormalized_probs]
            alias_nodes[node] = alias_setup(normalized_probs)

        alias_edges = {}

        if is_directed:
            for edge in G.edges():
                alias_edges[edge] = self.get_alias_edge(edge[0], edge[1])
        else:
            for edge in G.edges():
                alias_edges[edge] = self.get_alias_edge(edge[0], edge[1])
                alias_edges[(edge[1], edge[0])] = \
                    self.get_alias_edge(edge[1], edge[0])

        self.alias_nodes = alias_nodes
        self.alias_edges = alias_edges

        return


class WalkSimulation(object):

    def __init__(self, G, num_walks, walk_length, no_randomisation=False,
                 **kwargs):

        self.G = G
        self.num_walks = num_walks
        self.walk_length = walk_length
        self.shuffle = not no_randomisation
        self.walk_log = 0

    def __iter__(self):

        walks = []
        nodes = list(self.G.G.nodes()) if self.shuffle else self.G.G.nodes()
        logging.info('Walk iteration{}:'.format(self.walk_log))
        self.walk_log += 1
        for walk_iter in range(self.num_walks):
            logging.debug('%s/%s', str(walk_iter + 1), str(self.num_walks))
            if self.shuffle:
                random.shuffle(nodes)
            for node in nodes:
                yield [str(x) for x in
                       self.G.node2vec_walk(walk_length=self.walk_length,
                                            start_node=node)]


def alias_setup(probs):
    """
    Compute utility lists for non-uniform sampling from discrete distributions.
    Refer to https://tinyurl.com/ybz6xlcr
    for details
    """
    K = len(probs)
    q = np.zeros(K)
    J = np.zeros(K, dtype=np.int)

    smaller = []
    larger = []
    for kk, prob in enumerate(probs):
        q[kk] = K*prob
        if q[kk] < 1.0:
            smaller.append(kk)
        else:
            larger.append(kk)

    while len(smaller) > 0 and len(larger) > 0:
        small = smaller.pop()
        large = larger.pop()

        J[small] = large
        q[large] = q[large] + q[small] - 1.0
        if q[large] < 1.0:
            smaller.append(large)
        else:
            larger.append(large)

    return J, q


def alias_draw(J, q):
    """
    Draw sample from a non-uniform discrete distribution using alias sampling.
    """
    K = len(J)

    kk = int(np.floor(np.random.rand()*K))
    if np.random.rand() < q[kk]:
        return kk
    else:
        return J[kk]


def learn_embeddings(walks, dimensions, window_size, workers, n_iter,
                     output_path, **kwargs):
    """
    Learn embeddings by optimizing the Skipgram objective using SGD.
    """
    model = Word2Vec(walks, size=dimensions, window=window_size, min_count=0,
                     sg=1, workers=workers, iter=n_iter)
    model.wv.save_word2vec_format(output_path)


def read_graph(input_path, weighted, directed, **kwargs):
    """
    Reads the input network in networkx.
    """
    if weighted:
        G = nx.read_edgelist(input_path, nodetype=int,
                             data=(('weight', float),),
                             create_using=nx.DiGraph())
    else:
        G = nx.read_edgelist(input_path, nodetype=int,
                             create_using=nx.DiGraph())
        for edge in G.edges():
            G[edge[0]][edge[1]]['weight'] = 1

    if not directed:
        G = G.to_undirected()

    return G
